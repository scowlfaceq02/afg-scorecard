"""
fix_blanche_score.py — corrects the Blanche scorecard entry.

The Problem:
  id=83 was logged July 31 with BUY NO at 65% (AFG was fading Blanche).
  Blanche resolved YES (confirmed 50-49 on Aug 8).
  BUY NO + YES outcome = INCORRECT on the scorecard.

The Fix:
  AFG publicly reversed to BUY YES at 81% on August 7 — disclosed in the
  report and Publication Note before the Senate vote. The August 7 call is
  AFG's operative position at resolution. Per the last-call-before-resolution
  rule (amended August 2026), this call should score, not the July 31 call.

  This script:
  1. Voids id=83 (the July 31 BUY NO — wrong direction, does not score)
  2. Inserts the August 7 BUY YES and marks it Resolved/CORRECT
     OR updates an existing Aug 7 row if it already exists

Run:
    python3 fix_blanche_score.py
    python3 check_blanche.py
    python3 06_build_scorecard.py
    git add -A && git commit -m "fix Blanche score - last call rule" && git push
"""

from db import get_conn

TICKER       = "KXNEXTAG-29-TB"
KALSHI_PRICE = 0.81    # Aug 7 market price
AFG_PROB     = 0.88    # Aug 7 AFG estimate
OUTCOME      = 1       # YES — confirmed 50-49


def brier(prob, outcome):
    return round((outcome - prob) ** 2, 4)


def main():
    afg_brier    = brier(AFG_PROB, OUTCOME)
    kalshi_brier = brier(KALSHI_PRICE, OUTCOME)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, report_date, recommendation, status FROM predictions "
            "WHERE kalshi_ticker=? ORDER BY id",
            (TICKER,)
        ).fetchall()

        print(f"Current rows for {TICKER}:")
        for r in rows:
            print(f"  id={r[0]}  date={r[1]}  call={r[2]}  status={r[3]}")

        # Step 1: Void all existing rows — none should score
        ids = [r[0] for r in rows]
        if ids:
            conn.execute(
                f"UPDATE predictions SET status='Void', outcome=NULL, "
                f"brier_score=NULL, kalshi_brier_score=NULL "
                f"WHERE id IN ({','.join('?'*len(ids))})",
                ids
            )
            print(f"\nVoided {len(ids)} existing row(s)")

        # Step 2: Insert the August 7 BUY YES call and resolve it immediately
        conn.execute(
            """INSERT INTO predictions
               (market, category, kalshi_ticker, report_date, kalshi_price,
                afg_probability, edge_score, conviction, recommendation,
                contract_close_date, status, outcome, brier_score, kalshi_brier_score)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("Trump next Attorney General — Todd Blanche",
             "Politics", TICKER, "2026-08-07",
             KALSHI_PRICE, AFG_PROB,
             round(AFG_PROB - KALSHI_PRICE, 4),
             "MEDIUM", "BUY YES", "2029-01-20",
             "Resolved", OUTCOME, afg_brier, kalshi_brier)
        )
        conn.commit()

        new_id = conn.execute(
            "SELECT id FROM predictions WHERE kalshi_ticker=? AND status='Resolved' "
            "ORDER BY id DESC LIMIT 1",
            (TICKER,)
        ).fetchone()[0]

        print(f"Inserted Aug 7 BUY YES as id={new_id}")
        print(f"  Resolved: outcome=YES  AFG Brier={afg_brier}  "
              f"Kalshi Brier={kalshi_brier}  -> CORRECT")

    print("\nDone. Now run:")
    print("  python3 check_blanche.py")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m 'fix Blanche score last call rule' && git push")


if __name__ == "__main__":
    main()
