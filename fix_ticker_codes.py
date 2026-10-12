"""
fix_ticker_codes.py — one-time correction of contract codes in afg_scorecard.db.

WHY: audit_tickers.py (12 Oct 2026) showed that 36 stored codes were not real
Kalshi codes, so those calls could never resolve. The verified corrections now
live in afg_logging_rules.TICKER_ALIASES. This script applies them to the
database and fixes the three things a plain rename cannot:

  1. US-Iran nuclear deal: the 21 July 2026 call was on the "before Jan 1,
     2028" strike, but it was merged with the later "before Jan 20, 2029"
     calls under one code. That one row moves to KXUSAIRANAGREEMENT-27-28,
     and the true first call on the 2029 strike (22 July: BUY NO, AFG 20%
     vs Kalshi 57%), which the merge had hidden, is restored.
  2. Two contracts Kalshi settled before their stored close dates: the Fed
     hike by Dec 31 2026 (FEDHIKE-26DEC31, settled 16 Sept when the Fed
     hiked) and Big Brother/Dee (settled 25 Sept). Their stored close dates
     would trip the premature-resolution STOP in 06_build_scorecard.py once
     05 records the results, so they are set to the real dates.
  3. verified_early_resolutions.txt: any allowlisted code that was renamed is
     rewritten to its new code, or the Blanche early settlement would trip
     the STOP check.

This script does NOT resolve anything. After it runs, 05_update_scorecard.py
looks the corrected codes up on Kalshi and records the real results.

SAFE BY DEFAULT: without --apply it works on a temporary copy, prints exactly
what would change, and deletes the copy.

Run from C:\\Users\\qwhit\\AFG:
    python3 fix_ticker_codes.py            preview
    python3 fix_ticker_codes.py --apply    write changes (backs up first)
"""

import datetime
import os
import shutil
import sqlite3
import sys
import tempfile

import db
from afg_logging_rules import TICKER_ALIASES, canonicalize_db_tickers

ALLOWLIST = "verified_early_resolutions.txt"
IRAN_OLD = ("KXUSAIRANAGREEMENT-27-JAN29", "KXUSAIRANAGREEMENT-27-29JAN20")
IRAN_2028 = "KXUSAIRANAGREEMENT-27-28"
# Contracts Kalshi settled before the stored close date (dates from
# audit_tickers.py, 12 Oct 2026). Without this, 06_build_scorecard.py's
# premature-resolution STOP fires once 05 records the results.
CLOSE_DATE_FIXES = [
    ("FEDHIKE-26DEC31",          "2026-09-16"),  # Fed hiked 16 Sept
    ("KXBIGBROTHER-26DEC31-DEE", "2026-09-25"),  # Dee out; settled 25 Sept
]


def run(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    before = dict(conn.execute(
        "SELECT status, COUNT(*) FROM predictions GROUP BY status").fetchall())

    # 1. Split the 21 July Iran call onto its own strike BEFORE renaming.
    q = ("SELECT id, market, report_date, status FROM predictions WHERE kalshi_ticker IN (?,?) "
         "AND report_date='2026-07-21'")
    iran = conn.execute(q, IRAN_OLD).fetchall()
    for r in iran:
        if "2028" not in (r["market"] or ""):
            print(f"  STOP: row {r['id']} dated 2026-07-21 does not describe the 2028 "
                  f"strike ({r['market']!r}). Not moved — paste this output into chat.")
            continue
        conn.execute("UPDATE predictions SET kalshi_ticker=?, contract_close_date='2028-01-01' "
                     "WHERE id=?", (IRAN_2028, r["id"]))
        print(f"  Iran split: row {r['id']} [{r['status']}] ({r['market']}) -> {IRAN_2028}")
    if not iran:
        print("  Iran split: no 2026-07-21 row found under the merged code (nothing to move)")

    # 1b. Restore the true first call on the Jan 20 2029 strike (published
    # 22 July 2026: BUY NO, AFG 20% vs Kalshi 57%; afg_backfill_history.csv
    # line 64). Under the merged code it sat behind the 21 July 2028-strike
    # call, so it was either never stored or stored as Superseded.
    iran29 = "KXUSAIRANAGREEMENT-27-29JAN20"
    codes = (iran29,) + IRAN_OLD
    r22 = conn.execute(
        "SELECT id, status, market, recommendation, afg_probability, kalshi_price "
        "FROM predictions WHERE kalshi_ticker IN (?,?,?) AND report_date='2026-07-22' "
        "ORDER BY id", codes).fetchall()
    for r in r22:
        print(f"  Iran 22 July row {r['id']} [{r['status']}]: {r['recommendation']} "
              f"AFG {r['afg_probability']} vs Kalshi {r['kalshi_price']} ({r['market']})")
    sib = conn.execute(
        "SELECT afg_closed, afg_closed_date, afg_closed_reason FROM predictions "
        "WHERE kalshi_ticker IN (?,?,?) AND report_date NOT IN ('2026-07-21','2026-07-22') "
        "AND status IN ('Open','Resolved') ORDER BY report_date DESC LIMIT 1", codes).fetchone()
    live = [r for r in r22 if r["status"] in ("Open", "Resolved")]
    sup = [r for r in r22 if r["status"] == "Superseded"]
    if live:
        print("  Iran 2029 first call (2026-07-22): already live — nothing to do")
    elif sib is None:
        print("  STOP: no live 2029-strike rows found — Iran first call not restored; paste output into chat")
    elif sup:
        r = sup[0]
        good = ("2029" in (r["market"] or "") and r["recommendation"] == "BUY NO"
                and abs(float(r["afg_probability"]) - 0.20) < 0.005
                and abs(float(r["kalshi_price"]) - 0.57) < 0.005)
        if not good:
            print(f"  STOP: Superseded 22 July row {r['id']} does not match the published call "
                  "(BUY NO, 20% vs 57%). Not changed — paste this output into chat.")
        else:
            conn.execute("UPDATE predictions SET status='Open', kalshi_ticker=?, "
                         "contract_close_date='2029-01-20', afg_closed=?, afg_closed_date=?, "
                         "afg_closed_reason=? WHERE id=?",
                         (iran29, sib["afg_closed"], sib["afg_closed_date"],
                          sib["afg_closed_reason"], r["id"]))
            print(f"  Iran 2029 first call reinstated: row {r['id']} Superseded -> Open "
                  f"(closed flag copied from the position: {sib['afg_closed']})")
    else:
        conn.execute(
            """INSERT INTO predictions
               (market, category, kalshi_ticker, report_date, kalshi_price, afg_probability,
                edge_score, conviction, recommendation, contract_close_date, status,
                afg_closed, afg_closed_date, afg_closed_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'Open', ?,?,?)""",
            ("US-Iran nuclear deal before Jan 20 2029?", "Politics", iran29, "2026-07-22",
             0.57, 0.20, round(0.20 - 0.57, 4), "HIGH", "BUY NO", "2029-01-20",
             sib["afg_closed"], sib["afg_closed_date"], sib["afg_closed_reason"]))
        print("  Iran 2029 first call restored: 2026-07-22 BUY NO, AFG 20% vs Kalshi 57% "
              f"(closed flag copied from the position: {sib['afg_closed']})")

    # 2. Rename every aliased code.
    renames = canonicalize_db_tickers(conn)
    for old, new, n in renames:
        print(f"  Renamed {old:34s} -> {new:38s} ({n} row(s))")
    if not renames:
        print("  No codes to rename (already corrected).")

    # 3. Real close dates for contracts Kalshi settled early.
    for tkr, cdate in CLOSE_DATE_FIXES:
        n = conn.execute("UPDATE predictions SET contract_close_date=? WHERE kalshi_ticker=? "
                         "AND contract_close_date<>?", (cdate, tkr, cdate)).rowcount
        print(f"  Close date {tkr} -> {cdate} ({n} row(s))")

    conn.commit()
    after = dict(conn.execute(
        "SELECT status, COUNT(*) FROM predictions GROUP BY status").fetchall())
    conn.close()
    print(f"  Row counts by status before: {before}")
    print(f"  Row counts by status after : {after}  (nothing is resolved here)")
    diff = {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)
            if after.get(k, 0) != before.get(k, 0)}
    print(f"  Change in row counts: {diff or 'none'}")
    # Only allowed change: one Iran 2029 row becomes Open (inserted, or reinstated from Superseded).
    return diff in ({}, {"Open": 1}, {"Open": 1, "Superseded": -1})


def fix_allowlist(apply):
    if not os.path.exists(ALLOWLIST):
        print(f"  {ALLOWLIST} not found — nothing to update.")
        return
    lines = open(ALLOWLIST, encoding="utf-8").read().splitlines()
    out, changed = [], []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#"):
            parts = line.split("|")
            t = parts[0].strip()
            if t in TICKER_ALIASES:
                new = TICKER_ALIASES[t]
                parts[0] = parts[0].replace(t, new)
                line = "|".join(parts)
                changed.append((t, new))
        out.append(line)
    for t, new in changed:
        print(f"  Allowlist: {t} -> {new}")
    if not changed:
        print("  Allowlist: no renamed codes in it.")
    if apply and changed:
        shutil.copy(ALLOWLIST, ALLOWLIST + ".bak")
        with open(ALLOWLIST, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")


def main():
    apply = "--apply" in sys.argv
    if not os.path.exists(db.DB_PATH):
        print(f"ERROR: {db.DB_PATH} not found. Run from C:\\Users\\qwhit\\AFG.")
        sys.exit(1)
    if apply:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{db.DB_PATH}.before_ticker_fix_{stamp}"
        shutil.copy(db.DB_PATH, backup)
        print(f"Backup written: {backup}\n")
        ok = run(db.DB_PATH)
    else:
        tmp = os.path.join(tempfile.mkdtemp(), "preview.db")
        shutil.copy(db.DB_PATH, tmp)
        print("PREVIEW — working on a temporary copy. Nothing is written.\n")
        ok = run(tmp)
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    print("")
    fix_allowlist(apply)
    print("")
    if not ok:
        print("WARNING: unexpected change in row counts — do not continue; paste this output into chat.")
    elif apply:
        print("Done. Next: python3 05_update_scorecard.py  — then paste its output into chat "
              "BEFORE running 06 or pushing.")
    else:
        print("Preview only. To apply:  python3 fix_ticker_codes.py --apply")


if __name__ == "__main__":
    main()
