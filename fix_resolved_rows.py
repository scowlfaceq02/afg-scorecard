"""
fix_resolved_rows.py — makes every RESOLVED contract in afg_scorecard.db carry
exactly the calls AFG published, as audit_resolved_rows.py checks.

Found 12 Oct 2026 (audit_resolved_rows.py):
  * Blanche / next Attorney General: the 31 July BUY NO (first call) was Void,
    so the First-Call track scored the 7 August BUY YES — a published loss
    counted as a win.
  * Oregon drought: the 27 July BUY YES reversal (72%, HIGH) was Void, so the
    Updated-Position track scored the earlier BUY NO — a loss counted as a win.
  * Isaias first-hurricane and July hottest-month: AFG published NO TRADE
    (closing the position) before settlement, but the closure was never
    recorded, so Updated-Position scored them instead of excluding them.
    Both still score INCORRECT on First-Call and appear in Closed Positions.
  * Big Brother (Dee, Drew, Rick, Yash) and LeBron/Miami: duplicate or missing
    rows. No change to correct/incorrect, small Brier effect.

WHAT IT DOES, for each resolved contract only:
  - keeps live rows that match a published call
  - restores a published call from its hidden (Void/Superseded) row, keeping
    the original row id, or inserts it if no copy exists
  - marks live rows that match no published call as Void (kept for audit)
  - sets outcome and both Brier scores on every live row from the contract's
    recorded Kalshi result, and sets the closed flag to the published record
It never changes an outcome, and never touches an unresolved contract.

SAFE BY DEFAULT: without --apply it works on a temporary copy and prints every
change. With --apply it backs up the database first.

Run from C:\\Users\\qwhit\\AFG:
    python3 fix_resolved_rows.py            preview
    python3 fix_resolved_rows.py --apply    write changes
"""

import datetime
import os
import shutil
import sqlite3
import sys
import tempfile

import db
import afg_logging_rules as R
from audit_resolved_rows import replay, sig

COLS = ("market, category, kalshi_ticker, report_date, kalshi_price, afg_probability, "
        "edge_score, conviction, recommendation")


def fmt(r):
    return (f"{R.iso(r['report_date'])} {r['recommendation']} AFG {float(r['afg_probability']):.0%} "
            f"vs {float(r['kalshi_price']):.0%}")


def run(path, exp):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    R.ensure_columns(conn)
    before = dict(conn.execute("SELECT status, COUNT(*) FROM predictions GROUP BY status").fetchall())
    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT kalshi_ticker FROM predictions WHERE status='Resolved' ORDER BY 1")]
    ok = True
    changed = 0
    for t in tickers:
        res = conn.execute("SELECT DISTINCT outcome, contract_close_date FROM predictions "
                           "WHERE kalshi_ticker=? AND status='Resolved'", (t,)).fetchall()
        outcomes = {r[0] for r in res}
        if len(outcomes) != 1:
            print(f"  STOP {t}: resolved rows disagree on outcome {outcomes} — skipped")
            ok = False
            continue
        o = outcomes.pop()
        close = max(r[1] for r in res if r[1]) if any(r[1] for r in res) else None
        expected = [dict(r) for r in exp.execute(
            "SELECT * FROM predictions WHERE kalshi_ticker=? ORDER BY report_date, id", (t,))]
        if not expected:
            print(f"  NOTE {t}: not in published history — left unchanged")
            continue
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM predictions WHERE kalshi_ticker=? ORDER BY report_date, id", (t,))]
        live = [r for r in rows if r["status"] in ("Open", "Resolved")]
        hidden = [r for r in rows if r["status"] not in ("Open", "Resolved")]
        used = set()
        actions = []
        keep_ids = []
        for e in expected:
            m = next((r for r in live if r["id"] not in used and sig(r) == sig(e)), None)
            how = "kept"
            if m is None:
                m = next((r for r in hidden if r["id"] not in used and sig(r) == sig(e)), None)
                how = f"restored from {m['status']} row {m['id']}" if m else None
            if m is None:
                cur = conn.execute(
                    f"INSERT INTO predictions ({COLS}, contract_close_date, status) "
                    f"SELECT {COLS}, ?, 'Resolved' FROM (SELECT ? AS market, ? AS category, "
                    "? AS kalshi_ticker, ? AS report_date, ? AS kalshi_price, ? AS afg_probability, "
                    "? AS edge_score, ? AS conviction, ? AS recommendation)",
                    (close, e["market"], e["category"], t, R.iso(e["report_date"]), e["kalshi_price"],
                     e["afg_probability"], e["edge_score"], e["conviction"], e["recommendation"]))
                rid = cur.lastrowid
                how = "inserted (no stored copy)"
            else:
                rid = m["id"]
                used.add(rid)
            keep_ids.append(rid)
            if how != "kept":
                actions.append(f"    + {fmt(e)}  — {how}")
            # outcome, Brier, close date, closed flag from the published record
            afg_b = (float(e["afg_probability"]) - o) ** 2
            kal_b = (float(e["kalshi_price"]) - o) ** 2
            prev = conn.execute("SELECT status, outcome, COALESCE(afg_closed,0) FROM predictions "
                                "WHERE id=?", (rid,)).fetchone()
            conn.execute(
                "UPDATE predictions SET status='Resolved', outcome=?, brier_score=?, "
                "kalshi_brier_score=?, contract_close_date=?, afg_closed=?, afg_closed_date=?, "
                "afg_closed_reason=? WHERE id=?",
                (o, afg_b, kal_b, close, e["afg_closed"] or 0, e["afg_closed_date"],
                 e["afg_closed_reason"], rid))
            if how == "kept" and prev[2] != (e["afg_closed"] or 0):
                actions.append(f"    ~ {fmt(e)}  — closed flag {prev[2]} -> {e['afg_closed'] or 0}"
                               f" (published NO TRADE {e['afg_closed_date']})")
        for r in live:
            if r["id"] not in keep_ids:
                conn.execute("UPDATE predictions SET status='Void' WHERE id=?", (r["id"],))
                actions.append(f"    - {fmt(r)}  — row {r['id']} matches no published call -> Void")
        if actions:
            changed += 1
            print(f"  {t}  (outcome {'YES' if o == 1 else 'NO'})")
            for a in actions:
                print(a)
    conn.commit()
    after = dict(conn.execute("SELECT status, COUNT(*) FROM predictions GROUP BY status").fetchall())
    conn.close()
    print(f"\n  Contracts changed: {changed}")
    print(f"  Row counts before: {before}")
    print(f"  Row counts after : {after}")
    return ok


def main():
    apply = "--apply" in sys.argv
    exp = replay()
    if apply:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{db.DB_PATH}.before_resolved_fix_{stamp}"
        shutil.copy(db.DB_PATH, backup)
        print(f"Backup written: {backup}\n")
        ok = run(db.DB_PATH, exp)
    else:
        tmp = os.path.join(tempfile.mkdtemp(), "preview.db")
        shutil.copy(db.DB_PATH, tmp)
        print("PREVIEW — working on a temporary copy. Nothing is written.\n")
        ok = run(tmp, exp)
    print("")
    if not ok:
        print("WARNING: a contract was skipped — paste this output into chat before going further.")
    elif apply:
        print("Done. Next: python3 audit_resolved_rows.py (should show 0 needing review), "
              "then python3 06_build_scorecard.py — paste both outputs; do not push yet.")
    else:
        print("Preview only. To apply:  python3 fix_resolved_rows.py --apply")


if __name__ == "__main__":
    main()
