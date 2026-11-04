"""
fix_f1_close_date.py — the F1 Drivers' Championship contract (Antonelli)
settled early, so its stored close date must become the real settlement date.

Background (November 4th, 2026):
  Antonelli clinched the 2026 title at the Mexico City Grand Prix on
  November 1st. Kalshi has now settled KXF1-26-KA YES, as
  revert_premature_f1.py confirmed from your machine. 06_build_scorecard.py
  stopped because the stored close date (2026-12-07) is Kalshi's latest
  possible expiry, not the day it settled. This is the same situation
  fix_premature_resolution_dates.py handled for the hurricane and Big
  Brother contracts.

What it does:
  1. Reads the contract from Kalshi and stops, changing nothing, unless
     Kalshi reports it settled.
  2. Takes the settlement date from Kalshi's settlement timestamp
     (settlement_ts, or the latest of the other settlement fields). If
     Kalshi gives none, it uses today's date and says so.
  3. Checks that every Resolved row in the database matches Kalshi's
     result. If any row disagrees, it stops and changes nothing.
  4. Sets contract_close_date to the settlement date on every row of the
     contract (current ticker and old KXF1-26-ANT alias). It changes no
     outcome, Brier score or status.

AFG's July 27th first call was BUY NO at 70% against 75%, so it scores
INCORRECT on the First-Call track. That is correct and stays as it is.

Safe to run more than once.

Run from C:\\Users\\qwhit\\AFG:
    python3 fix_f1_close_date.py
    python3 06_build_scorecard.py      (paste the output; do not push yet)
"""

import datetime

from db import get_conn
from kalshi_client import get_market

TICKER = "KXF1-26-KA"
TICKERS = ("KXF1-26-KA", "KXF1-26-ANT")
SETTLE_FIELDS = ("settlement_ts", "settlement_time", "determination_time",
                 "settled_time", "expiration_time", "close_time")


def main():
    try:
        m = get_market(TICKER)
    except Exception as e:
        print(f"Could not reach Kalshi ({e}). Nothing changed. Try again.")
        return

    status, result = m.get("status"), m.get("result")
    print(f"Kalshi {TICKER}: status={status!r} result={result!r}")
    for f in SETTLE_FIELDS:
        if m.get(f):
            print(f"  {f}: {m[f]}")
    if status not in ("settled", "finalized") or result not in ("yes", "no"):
        print("Kalshi does not report this contract settled. Nothing changed.")
        return

    # Settlement date: prefer an explicit settlement timestamp
    settle_date, source = None, None
    for f in ("settlement_ts", "settlement_time", "determination_time", "settled_time"):
        if m.get(f):
            settle_date, source = str(m[f])[:10], f
            break
    today = datetime.date.today().isoformat()
    if settle_date is None:
        settle_date, source = today, "today's date (Kalshi gave no settlement timestamp)"
    if settle_date > today:
        print(f"Settlement date {settle_date} is in the future. Nothing changed.")
        return
    print(f"\nSettlement date: {settle_date}  (from {source})")

    kalshi_outcome = 1 if result == "yes" else 0
    with get_conn() as conn:
        q = ",".join("?" * len(TICKERS))
        rows = conn.execute(
            f"SELECT id, kalshi_ticker, report_date, recommendation, kalshi_price, "
            f"afg_probability, status, outcome, contract_close_date "
            f"FROM predictions WHERE kalshi_ticker IN ({q}) ORDER BY id", TICKERS
        ).fetchall()
        if not rows:
            print("No rows found for", TICKERS, "- nothing changed.")
            return
        print("\nRows:")
        for r in rows:
            print(f"  id={r['id']:<4} {r['kalshi_ticker']:<12} {r['report_date']}  "
                  f"{r['recommendation']:<8} Kalshi {r['kalshi_price']:.0%} "
                  f"AFG {r['afg_probability']:.0%}  status={r['status']}  "
                  f"outcome={r['outcome']}  close={r['contract_close_date']}")

        bad = [r for r in rows if r["status"] == "Resolved" and r["outcome"] != kalshi_outcome]
        if bad:
            print(f"\nSTOP: {len(bad)} Resolved row(s) disagree with Kalshi's result "
                  f"({result.upper()}). Nothing changed. Paste this output to Claude.")
            return

        n = conn.execute(
            f"UPDATE predictions SET contract_close_date=? "
            f"WHERE kalshi_ticker IN ({q}) "
            f"AND (contract_close_date IS NULL OR contract_close_date<>?)",
            (settle_date, *TICKERS, settle_date)
        ).rowcount
        conn.commit()

    print(f"\nSet close date to {settle_date} on {n} row(s). "
          f"Outcomes unchanged: all Resolved rows match Kalshi ({result.upper()}).")
    print("Next: python3 06_build_scorecard.py and paste the output. Do not push yet.")


if __name__ == "__main__":
    main()
