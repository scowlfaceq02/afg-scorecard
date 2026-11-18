"""
fix_bond_resolution.py  --  records the James Bond early settlement (November 18th, 2026)
=======================================================================================
Amazon MGM named Robert Pattinson as James Bond on November 16th, 2026, and Kalshi
settled every KXBOND-30 contract that day, years before the contracts' official
close date of January 1st, 2030. verify_afg.py (check 5) therefore saw resolved
Bond rows with a future close date and no resolution date, and stopped the cycle.

This script, for every active KXBOND-30 row in afg_scorecard.db:
  1. asks Kalshi for the contract's settlement (stops, changing nothing, if Kalshi
     cannot be reached or the contract is not settled),
  2. sets outcome from Kalshi's result (1 = Yes, 0 = No), so Robert Pattinson is
     recorded as settled Yes even if his row had no outcome yet,
  3. sets resolution_date = 2026-11-16, the announcement date.

It shows every row before and after, and changes nothing unless every Bond
contract in the database is confirmed settled by Kalshi.

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 fix_bond_resolution.py          (shows what it would change, changes nothing)
    python3 fix_bond_resolution.py --apply  (makes the change)
Then run run_cycle.py again.
"""
import sqlite3
import sys

from check_settlements import fetch_market, NotFound

DB_PATH = "afg_scorecard.db"
PREFIX = "KXBOND-30-"
RESOLUTION_DATE = "2026-11-16"
ACTIVE = "status NOT IN ('Void','Superseded')"


def main(db_path=DB_PATH, apply=False, fetch=fetch_market):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"""SELECT id, ticker, market, recommendation, outcome, close_date, resolution_date
                    FROM predictions WHERE ticker LIKE ? AND {ACTIVE} ORDER BY ticker, id""",
                (PREFIX + "%",))
    rows = cur.fetchall()
    if not rows:
        print("No active KXBOND-30 rows found. Nothing to do.")
        return 0

    print("Before:")
    for r in rows:
        print(f"  id={r[0]:<5} {r[1]:<22} {r[3]:<9} outcome={r[4]}  close={r[5]}  resolution={r[6]}")

    # 1. confirm every Bond contract with Kalshi before touching anything
    results = {}
    for ticker in sorted({r[1] for r in rows}):
        try:
            m = fetch(ticker)
        except NotFound:
            print(f"\nSTOP: Kalshi has no record of {ticker}. Nothing changed.")
            return 1
        except Exception as e:
            print(f"\nSTOP: could not reach Kalshi for {ticker} ({e}). Nothing changed.")
            return 1
        result = str(m.get("result", "")).lower()
        if result not in ("yes", "no"):
            print(f"\nSTOP: Kalshi shows {ticker} as '{m.get('status')}' with no Yes/No result. Nothing changed.")
            return 1
        results[ticker] = 1 if result == "yes" else 0
        print(f"  Kalshi: {ticker:<22} status={m.get('status')}  result={result.upper()}")

    if sum(results.values()) > 1:
        print("\nSTOP: Kalshi shows more than one Bond contract settled Yes. Check by hand. Nothing changed.")
        return 1

    # 2. show the change
    print("\nChange:")
    changes = []
    for r in rows:
        rid, ticker, _, rec, outcome, _, res = r
        new_outcome = results[ticker]
        if outcome != new_outcome or res != RESOLUTION_DATE:
            changes.append((new_outcome, RESOLUTION_DATE, rid))
            print(f"  id={rid:<5} {ticker:<22} outcome {outcome} -> {new_outcome}   resolution {res} -> {RESOLUTION_DATE}")
    if not changes:
        print("  none. The Bond rows are already recorded correctly.")
        return 0

    if not apply:
        print(f"\nDRY RUN: {len(changes)} row(s) would change. Run with --apply to make the change.")
        return 0

    cur.executemany("UPDATE predictions SET outcome=?, resolution_date=? WHERE id=?", changes)
    conn.commit()
    print(f"\nUpdated {len(changes)} row(s).\n\nAfter:")
    cur.execute(f"""SELECT id, ticker, recommendation, outcome, close_date, resolution_date
                    FROM predictions WHERE ticker LIKE ? AND {ACTIVE} ORDER BY ticker, id""",
                (PREFIX + "%",))
    for r in cur.fetchall():
        print(f"  id={r[0]:<5} {r[1]:<22} {r[2]:<9} outcome={r[3]}  close={r[4]}  resolution={r[5]}")
    conn.close()
    print("\nDone. Run run_cycle.py again; verify_afg.py check 5 should now pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))
