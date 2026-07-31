"""
045_log_predictions.py — logs this cycle's approved predictions into the
scorecard database automatically, so the scorecard can resolve them later.

Runs right after 04_build_report.py. Idempotent per TICKER: a market that
has already been logged (regardless of report date) will not be logged again.
This prevents the same contract accumulating duplicate rows across cycles.

Run:
    python3 045_log_predictions.py
"""

import os
import sys
import pandas as pd

from db import get_conn, add_predictions_bulk

APPROVED_CSV = "data/approved_predictions.csv"


def already_logged_tickers():
    """Return the set of kalshi_tickers already in the database."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT kalshi_ticker FROM predictions "
            "WHERE kalshi_ticker IS NOT NULL"
        ).fetchall()
    return {row[0] for row in rows}


def main():
    if not os.path.exists(APPROVED_CSV):
        print(f"ERROR: {APPROVED_CSV} not found. Run Phase 4 first.")
        sys.exit(1)

    df = pd.read_csv(APPROVED_CSV)
    if df.empty:
        print("No rows to log.")
        return

    report_date = str(df.iloc[0]["report_date"])
    logged = already_logged_tickers()

    rows = []
    skipped = []
    for _, r in df.iterrows():
        rec = str(r["recommendation"]).upper()
        if "BUY YES" not in rec and "BUY NO" not in rec:
            continue  # NO TRADE — not scored

        ticker = r.get("kalshi_ticker")
        ticker = str(ticker) if pd.notna(ticker) else None

        # Skip if this ticker is already in the DB (first-call-only rule)
        if ticker and ticker in logged:
            skipped.append(ticker)
            continue

        rows.append({
            "market":              r["market"],
            "category":            r["category"],
            "kalshi_ticker":       ticker,
            "report_date":         report_date,
            "kalshi_price":        float(r["kalshi_price"]),
            "afg_probability":     float(r["afg_probability"]),
            "conviction":          r["conviction"],
            "recommendation":      "BUY YES" if "BUY YES" in rec else "BUY NO",
            "contract_close_date": (r.get("contract_close_date")
                                    if pd.notna(r.get("contract_close_date"))
                                    else None),
        })

    if skipped:
        print(f"  {len(skipped)} ticker(s) already logged — skipped "
              f"(first-call-only rule): {', '.join(skipped[:5])}"
              + (" ..." if len(skipped) > 5 else ""))

    if not rows:
        print("No new actionable calls to log this cycle.")
        return

    add_predictions_bulk(rows)
    missing = [r["market"] for r in rows if not r["kalshi_ticker"]]
    print(f"Logged {len(rows)} new call(s) for {report_date}.")
    if missing:
        print(f"  {len(missing)} without a ticker (needs backfill to auto-resolve):")
        for m in missing:
            print(f"    - {m}")


if __name__ == "__main__":
    main()
