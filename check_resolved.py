"""
check_resolved.py — shows every prediction currently marked Resolved
in the scorecard database, so each can be verified against actual
Kalshi settlement before anything is published.

Run:
    python3 check_resolved.py
"""

from db import get_conn


def main():
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT market, category, kalshi_ticker, report_date,
                      kalshi_price, afg_probability, conviction,
                      recommendation, outcome, contract_close_date,
                      brier_score, kalshi_brier_score
               FROM predictions
               WHERE status = 'Resolved'
               ORDER BY contract_close_date"""
        ).fetchall()]

    if not rows:
        print("No resolved predictions in the database.")
        return

    print(f"\n{'='*78}")
    print(f"  {len(rows)} RESOLVED PREDICTION(S) — VERIFY EACH BEFORE PUBLISHING")
    print(f"{'='*78}\n")

    for i, r in enumerate(rows, 1):
        outcome_txt = "YES" if r["outcome"] == 1 else "NO"
        # Was the call correct?
        if r["recommendation"] == "BUY YES":
            hit = (r["outcome"] == 1)
        elif r["recommendation"] == "BUY NO":
            hit = (r["outcome"] == 0)
        else:
            hit = None
        hit_txt = "CORRECT" if hit else ("INCORRECT" if hit is False else "N/A")

        print(f"[{i}] {r['market']}")
        print(f"     Category      : {r['category']}")
        print(f"     Ticker        : {r['kalshi_ticker']}")
        print(f"     Report date   : {r['report_date']}")
        print(f"     Close date    : {r['contract_close_date']}")
        print(f"     Kalshi price  : {r['kalshi_price']:.0%}")
        print(f"     AFG estimate  : {r['afg_probability']:.0%}")
        print(f"     Conviction    : {r['conviction']}")
        print(f"     AFG called    : {r['recommendation']}")
        print(f"     Outcome logged: {outcome_txt}  ->  {hit_txt}")
        print(f"     Brier (AFG)   : {r['brier_score']:.4f}"
              if r["brier_score"] is not None else "     Brier (AFG)   : —")
        print()

    print(f"{'='*78}")
    print("  ACTION REQUIRED: confirm each market above actually settled")
    print("  on Kalshi with the outcome shown. If any did NOT settle,")
    print("  it must be reset to Open before the scorecard is published.")
    print(f"{'='*78}\n")


if __name__ == "__main__":
    main()
