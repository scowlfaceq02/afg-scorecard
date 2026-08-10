"""
fix_blanche_resolution.py — logs the Todd Blanche confirmation and marks
it Resolved in one step.

Confirmed: Senate voted 50-49 early Saturday August 8, 2026.
AFG called BUY YES at 88% against an 81% market on August 7.
Outcome = YES (confirmed). This is a CORRECT call.

Run:
    python3 fix_blanche_resolution.py
    python3 check_resolved.py
    python3 06_build_scorecard.py
    git add -A && git commit -m "scorecard update Blanche confirmed" && git push
"""

from db import get_conn


TICKER       = "KXNEXTAG-29-TB"
KALSHI_PRICE = 0.81    # market price when AFG published on August 7
AFG_PROB     = 0.88    # AFG estimate
OUTCOME      = 1       # YES — Blanche confirmed


def brier(prob, outcome):
    return round((outcome - prob) ** 2, 4)


def main():
    afg_brier    = brier(AFG_PROB, OUTCOME)
    kalshi_brier = brier(KALSHI_PRICE, OUTCOME)

    with get_conn() as conn:
        # Check for any existing rows with this ticker
        existing = conn.execute(
            "SELECT id, status, outcome FROM predictions WHERE kalshi_ticker = ?",
            (TICKER,)
        ).fetchall()

        if existing:
            # Check if already resolved correctly
            resolved = [r for r in existing if r[1] == "Resolved"]
            if resolved:
                print(f"Already resolved ({len(resolved)} row(s)):")
                for r in resolved:
                    print(f"  id={r[0]}  status={r[1]}  outcome={r[2]}")
                print("Nothing to do.")
                return

            # Open rows exist — resolve the earliest, void the rest
            open_rows = sorted(
                [r for r in existing if r[1] == "Open"],
                key=lambda r: r[0]
            )
            void_rows = [r for r in existing if r[1] not in ("Resolved", "Void")]

            if open_rows:
                first_id = open_rows[0][0]
                conn.execute(
                    """UPDATE predictions
                       SET status='Resolved', outcome=?,
                           brier_score=?, kalshi_brier_score=?
                       WHERE id=?""",
                    (OUTCOME, afg_brier, kalshi_brier, first_id)
                )
                print(f"Resolved id={first_id}: outcome=YES  "
                      f"AFG Brier={afg_brier}  Kalshi Brier={kalshi_brier}  -> CORRECT")

                # Void any duplicates
                for r in open_rows[1:]:
                    conn.execute(
                        "UPDATE predictions SET status='Void' WHERE id=?",
                        (r[0],)
                    )
                    print(f"Voided duplicate id={r[0]}")

                conn.commit()
                return

        # No rows at all — insert fresh and resolve immediately
        conn.execute(
            """INSERT INTO predictions
               (market, category, kalshi_ticker, report_date, kalshi_price,
                afg_probability, edge_score, conviction, recommendation,
                contract_close_date)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("Trump next Attorney General — Todd Blanche",
             "Politics", TICKER, "2026-08-07",
             KALSHI_PRICE, AFG_PROB,
             round(AFG_PROB - KALSHI_PRICE, 4),
             "MEDIUM", "BUY YES", "2029-01-20")
        )
        conn.commit()

        pid = conn.execute(
            "SELECT id FROM predictions WHERE kalshi_ticker=? ORDER BY id DESC LIMIT 1",
            (TICKER,)
        ).fetchone()[0]
        print(f"Inserted prediction id={pid}")

        conn.execute(
            """UPDATE predictions
               SET status='Resolved', outcome=?,
                   brier_score=?, kalshi_brier_score=?
               WHERE id=?""",
            (OUTCOME, afg_brier, kalshi_brier, pid)
        )
        conn.commit()
        print(f"Resolved: outcome=YES  AFG Brier={afg_brier}  "
              f"Kalshi Brier={kalshi_brier}  -> CORRECT")

    print("\nDone. Now run:")
    print("  python3 check_resolved.py")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m \"scorecard Blanche confirmed\" && git push")


if __name__ == "__main__":
    main()
