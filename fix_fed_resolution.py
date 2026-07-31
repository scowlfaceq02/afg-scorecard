"""
fix_fed_resolution.py — one-time script to manually log the
Fed July 29 decision and mark it resolved.

Run once:
    python3 fix_fed_resolution.py

Safe to run multiple times — checks for duplicates first.
"""

from db import get_conn, add_prediction, record_outcome


def main():
    ticker = "KXFEDDECISION-26JUL-H0"

    # Check if already logged
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, status FROM predictions WHERE kalshi_ticker = ?",
            (ticker,)
        ).fetchall()

    if existing:
        print(f"Already in database ({len(existing)} row(s)):")
        for row in existing:
            print(f"  id={row[0]}  status={row[1]}")
        print("No action needed.")
        return

    # Log the prediction
    pid = add_prediction(
        market="Fed decision in July — Maintains rate",
        category="Economics",
        kalshi_ticker=ticker,
        report_date="2026-07-28",
        kalshi_price=0.75,
        afg_probability=0.88,
        conviction="HIGH",
        recommendation="BUY YES",
        contract_close_date="2026-07-29",
    )
    print(f"Logged prediction id={pid}")

    # Record the outcome: Fed held (YES = maintains rate = outcome 1)
    record_outcome(pid, 1)
    print("Outcome recorded: YES (Fed held at 3.50-3.75%) -> CORRECT")
    print("")
    print("Now run:")
    print("  python3 06_build_scorecard.py")
    print("  git add -A && git commit -m \"scorecard update - Fed resolved\" && git push")


if __name__ == "__main__":
    main()
