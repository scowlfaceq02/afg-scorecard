"""
revert_premature_f1.py — puts the F1 Drivers' Championship (Antonelli) rows
back to Open until Kalshi actually settles the contract.

Why (checked November 4th, 2026):
  Antonelli clinched the 2026 title at the Mexico City Grand Prix on
  November 1st, but Kalshi has not settled KXF1-26-KA. Kalshi's API shows
  status "active", no result, last price 99 cents, and an expected
  expiration of December 8th. AFG's scorecard is scored against Kalshi
  settlement, so these rows must not show as Resolved yet. Nothing is
  hidden by this: when Kalshi settles YES, 05_update_scorecard.py will
  resolve the rows automatically and the July 27th BUY NO (70% against
  75%) will score INCORRECT on the First-Call track.

What it does:
  1. Asks Kalshi for the contract's status. If Kalshi reports it settled,
     it stops and changes nothing (the right fix then is the close date,
     as in fix_premature_resolution_dates.py, not a revert).
  2. Prints every row for the contract (both the current ticker and the
     old KXF1-26-ANT alias) so you can see how it came to be Resolved.
  3. Sets Resolved rows back to Open and clears outcome and both Brier
     scores. It touches no other column and no other contract.

Safe to run more than once.

Run from C:\\Users\\qwhit\\AFG:
    python3 revert_premature_f1.py
    python3 06_build_scorecard.py      (paste the output; do not push yet)
"""

from db import get_conn
from kalshi_client import get_market_status

TICKERS = ("KXF1-26-KA", "KXF1-26-ANT")   # current ticker and the old alias


def main():
    try:
        status = get_market_status("KXF1-26-KA")
    except Exception as e:
        print(f"Could not reach Kalshi ({e}). Nothing changed. Try again.")
        return
    if status["settled"]:
        print(f"Kalshi reports KXF1-26-KA SETTLED ({status['result']}). "
              "Nothing changed. The contract settled early, so fix its "
              "close date instead of reverting.")
        return
    print("Kalshi: KXF1-26-KA is not settled. Reverting any Resolved rows.\n")

    with get_conn() as conn:
        q = ",".join("?" * len(TICKERS))
        rows = conn.execute(
            f"SELECT id, kalshi_ticker, report_date, recommendation, kalshi_price, "
            f"afg_probability, status, outcome, contract_close_date "
            f"FROM predictions WHERE kalshi_ticker IN ({q}) ORDER BY id", TICKERS
        ).fetchall()
        if not rows:
            print("No rows found for", TICKERS)
            return
        print("Rows before:")
        for r in rows:
            print(f"  id={r['id']:<4} {r['kalshi_ticker']:<12} {r['report_date']}  "
                  f"{r['recommendation']:<8} Kalshi {r['kalshi_price']:.0%} "
                  f"AFG {r['afg_probability']:.0%}  status={r['status']}  "
                  f"outcome={r['outcome']}  close={r['contract_close_date']}")

        n = conn.execute(
            f"UPDATE predictions SET status='Open', outcome=NULL, "
            f"brier_score=NULL, kalshi_brier_score=NULL "
            f"WHERE kalshi_ticker IN ({q}) AND status='Resolved'", TICKERS
        ).rowcount
        conn.commit()
        print(f"\nReverted {n} row(s) to Open.")

    print("\nNext: python3 06_build_scorecard.py and paste the output. Do not push yet.")


if __name__ == "__main__":
    main()
