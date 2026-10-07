"""
backfill_scorecard.py — loads every published AFG call that never reached the
scorecard database, using the same rules as 045_log_predictions.py.

WHY: predictions stopped being logged after 7 August 2026, so roughly two
months of published calls (including the 14 August hurricane call, the Bond
fades and the hottest-year calls) were never recorded and could not score.

WHAT IT DOES, in order:
  1. Backs up afg_scorecard.db (only with --apply)
  2. Converts every stored date to ISO format (2026-07-21). Mixed formats made
     a later call look earlier than the true first call when compared as text.
  3. Merges duplicate ticker spellings for the same contract
  4. Replays every published cycle from afg_backfill_history.csv in date
     order through afg_logging_rules.process_cycle
  5. Corrects the three Big Brother rows entered by hand on 2 October to the
     true first-call dates and prices
  6. Prints a full report

SAFE BY DEFAULT: without --apply it runs on a temporary copy of the database,
prints exactly what would change, and deletes the copy. Nothing is written.

Excluded dates (not published, so they cannot score):
  2026-07-18  pre-launch build
  2026-09-07  Labor Day — built but not published

Usage (from C:\\Users\\qwhit\\AFG):
    python3 backfill_scorecard.py            preview only
    python3 backfill_scorecard.py --apply    write changes (backs up first)
"""

import os
import shutil
import sqlite3
import sys
import datetime
from collections import Counter, defaultdict

import pandas as pd

import db
from afg_logging_rules import (canon, direction, ensure_columns, normalize_dates,
                               canonicalize_db_tickers, process_cycle)

HISTORY_CSV = "afg_backfill_history.csv"
EXCLUDED_DATES = {"2026-07-18", "2026-09-07"}

# Withdrawals AFG published for contracts that were NOT in that cycle's pull,
# so no NO TRADE row exists in the history to close them. Applied after replay.
MANUAL_CLOSURES = {
    "KXHURCTOTMAJ-26DEC01-0": ("2026-10-07",
        "Withdrawn: Isaias forecast to rapidly intensify; thesis no longer applies"),
}

# Rows inserted by hand on 2 October with estimated values; corrected to the
# true first published call.
MANUAL_BB_TICKERS = {
    "KXBIGBROTHER-26DEC31-DV",
    "KXBIGBROTHER-26DEC31-RIC",
    "KXBIGBROTHER-26DEC31-YAS",
    "KXBIGBROTHER-26DEC31-DRE",
}


def correct_manual_bb_rows(conn, history, events):
    for ticker in MANUAL_BB_TICKERS:
        h = history[(history["ticker_c"] == ticker) &
                    (history["recommendation"].str.upper().str.contains("BUY", na=False))]
        if h.empty:
            continue
        first = h.sort_values("report_date").iloc[0]
        row = conn.execute(
            "SELECT id, report_date, outcome, afg_probability, kalshi_price, brier_score "
            "FROM predictions WHERE kalshi_ticker=? AND status='Resolved' "
            "ORDER BY report_date, id LIMIT 1", (ticker,)).fetchone()
        if row is None or row["outcome"] is None:
            continue
        afg_p, kal_p, o = float(first["afg_probability"]), float(first["kalshi_price"]), int(row["outcome"])
        target = (first["report_date"], round(afg_p, 4), round(kal_p, 4), round((afg_p - o) ** 2, 4))
        current = (row["report_date"], round(float(row["afg_probability"] or -1), 4),
                   round(float(row["kalshi_price"] or -1), 4), round(float(row["brier_score"] or -1), 4))
        if current == target:
            continue
        conn.execute(
            """UPDATE predictions SET report_date=?, kalshi_price=?, afg_probability=?,
               edge_score=?, conviction=?, recommendation=?, brier_score=?,
               kalshi_brier_score=? WHERE id=?""",
            (first["report_date"], kal_p, afg_p, round(afg_p - kal_p, 4),
             first["conviction"], direction(first["recommendation"]),
             round((afg_p - o) ** 2, 4), round((kal_p - o) ** 2, 4), row["id"]))
        events.append(("bbfix", ticker, first["market"],
                       f"first call corrected {row['report_date']} -> {first['report_date']} "
                       f"(AFG {afg_p:.0%} vs Kalshi {kal_p:.0%})"))


def run(db_path, history):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    events = []
    ensure_columns(conn)
    n_dates = normalize_dates(conn)
    renames = canonicalize_db_tickers(conn)

    before = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE status IN ('Open','Resolved')").fetchone()[0]

    # Set aside existing OPEN rows for every contract in the published history
    # that has not resolved. Those rows were written by the old logger, which
    # kept only some calls and could hold a later call than the first one.
    # Replaying history on top of them produced false reversals (Odyssey).
    # Rebuilding from the published record is the only reliable source.
    # Resolved rows are never touched. Superseded rows are kept for audit.
    superseded = 0
    for ticker in sorted(history["kalshi_ticker"].dropna().unique()):
        resolved = conn.execute(
            "SELECT 1 FROM predictions WHERE kalshi_ticker=? AND status='Resolved' LIMIT 1",
            (ticker,)).fetchone()
        if resolved:
            continue
        superseded += conn.execute(
            "UPDATE predictions SET status='Superseded' WHERE kalshi_ticker=? AND status='Open'",
            (ticker,)).rowcount
    events.append(("superseded", None, None, superseded))

    for report_date, cycle in history.groupby("report_date", sort=True):
        process_cycle(conn, report_date, cycle.to_dict("records"), events)

    for ticker, (cdate, reason) in MANUAL_CLOSURES.items():
        n = conn.execute(
            "UPDATE predictions SET afg_closed=1, afg_closed_date=?, afg_closed_reason=? "
            "WHERE kalshi_ticker=? AND status='Open'", (cdate, reason, ticker)).rowcount
        if n:
            events.append(("closed", ticker, "manual withdrawal", f"closed {cdate}"))

    correct_manual_bb_rows(conn, history, events)
    conn.commit()

    after = conn.execute(
        "SELECT COUNT(*) FROM predictions WHERE status IN ('Open','Resolved')").fetchone()[0]
    stats = {
        "open": conn.execute("SELECT COUNT(*) FROM predictions WHERE status='Open'").fetchone()[0],
        "resolved": conn.execute("SELECT COUNT(*) FROM predictions WHERE status='Resolved'").fetchone()[0],
        "closed_open": conn.execute(
            "SELECT COUNT(DISTINCT kalshi_ticker) FROM predictions "
            "WHERE status='Open' AND afg_closed=1").fetchone()[0],
    }
    conn.close()
    return events, n_dates, renames, before, after, stats


def report(events, n_dates, renames, before, after, stats, applied):
    kinds = Counter(e[0] for e in events)
    title = "BACKFILL APPLIED" if applied else "BACKFILL PREVIEW — nothing has been written"
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(f"Dates converted to ISO format : {n_dates} row(s)")
    sup = sum(e[3] for e in events if e[0] == "superseded")
    print(f"Old open rows set aside       : {sup} (kept as 'Superseded' for audit)")
    print(f"Ticker spellings merged       : {sum(n for _, _, n in renames)} row(s)")
    for old, new, n in renames:
        print(f"    {old}  ->  {new}  ({n})")
    print(f"First calls added             : {kinds['first']}")
    print(f"Reversals added               : {kinds['reversal']}")
    print(f"Positions closed (NO TRADE)   : {kinds['closed']}")
    print(f"Positions reopened            : {kinds['reopen']}")
    print(f"Big Brother rows corrected    : {kinds['bbfix']}")
    print(f"Warnings                      : {kinds['warn']}")
    print(f"Active rows before / after    : {before} / {after}")
    rev_counts = Counter(e[1] for e in events if e[0] == "reversal")
    dup = {t: n for t, n in rev_counts.items() if n > 2}
    if dup:
        print("\n*** STOP: a contract shows more than two reversals — do not apply. "
              "Paste this output into the chat. ***")
        for t, n in dup.items():
            print(f"    {t}: {n} reversals")

    section = {"first": "FIRST CALLS ADDED", "reversal": "REVERSALS ADDED",
               "reopen": "REOPENED", "bbfix": "BIG BROTHER CORRECTIONS", "warn": "WARNINGS"}
    for kind, label in section.items():
        items = [e for e in events if e[0] == kind]
        if not items:
            continue
        print(f"\n{label}")
        for _, t, m, d in items:
            print(f"  {str(t):34s} {str(m)[:40]:40s} {d}")

    # Closures: report the final state only (a contract can close and reopen)
    final_close = {}
    for kind, t, m, d in events:
        if kind == "closed":
            final_close[t] = (m, d)
        elif kind == "reopen":
            final_close.pop(t, None)
    if final_close:
        print("\nCURRENTLY CLOSED (last published call was NO TRADE)")
        for t, (m, d) in sorted(final_close.items()):
            print(f"  {t:34s} {str(m)[:40]:40s} {d}")

    print("\nDatabase after backfill:")
    print(f"  Open rows     : {stats['open']}  ({stats['closed_open']} contract(s) marked closed)")
    print(f"  Resolved rows : {stats['resolved']}")
    if not applied:
        print("\nNothing was written. To apply:  python3 backfill_scorecard.py --apply")
    else:
        print("\nNext steps:")
        print("  python3 validate_tickers.py")
        print("  python3 05_update_scorecard.py")
        print("  python3 06_build_scorecard.py")
        print('  git add -A && git commit -m "scorecard backfill" && git push')


def main():
    apply = "--apply" in sys.argv
    if not os.path.exists(db.DB_PATH):
        print(f"ERROR: {db.DB_PATH} not found. Run this from C:\\Users\\qwhit\\AFG")
        sys.exit(1)
    if not os.path.exists(HISTORY_CSV):
        print(f"ERROR: {HISTORY_CSV} not found. Put it in the same folder as this script.")
        sys.exit(1)

    history = pd.read_csv(HISTORY_CSV)
    history["report_date"] = pd.to_datetime(history["report_date"]).dt.strftime("%Y-%m-%d")
    history = history[~history["report_date"].isin(EXCLUDED_DATES)].copy()
    history["ticker_c"] = history["kalshi_ticker"].map(canon)
    history["kalshi_ticker"] = history["ticker_c"]

    if apply:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"afg_scorecard_backup_{stamp}.db"
        shutil.copy2(db.DB_PATH, backup)
        print(f"Backup written: {backup}")
        target = db.DB_PATH
    else:
        target = "_backfill_preview.db"
        shutil.copy2(db.DB_PATH, target)

    try:
        result = run(target, history)
    finally:
        if not apply and os.path.exists(target):
            os.remove(target)

    report(*result, applied=apply)


if __name__ == "__main__":
    main()
