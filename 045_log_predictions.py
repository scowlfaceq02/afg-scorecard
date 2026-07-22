"""
045_log_predictions.py — logs this cycle's approved predictions into the
scorecard database automatically, so the scorecard can resolve them later.

Runs right after 04_build_report.py, before publishing. Idempotent: it will
not double-log the same market on the same report_date if run twice.

Run:
    python 045_log_predictions.py
"""

import os
import sys
import pandas as pd

from db import get_conn, add_predictions_bulk

APPROVED_CSV = "data/approved_predictions.csv"


def already_logged(report_date):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions WHERE report_date = ?",
            (report_date,),
        ).fetchone()
        return row["n"] > 0


def main():
    if not os.path.exists(APPROVED_CSV):
        print(f"ERROR: {APPROVED_CSV} not found. Run the pipeline through Phase 4 first.")
        sys.exit(1)

    df = pd.read_csv(APPROVED_CSV)
    if df.empty:
        print("No rows to log.")
        return

    report_date = str(df.iloc[0]["report_date"])
    if already_logged(report_date):
        print(f"Predictions for {report_date} already logged — skipping (idempotent).")
        return

    rows = []
    for _, r in df.iterrows():
        rec = str(r["recommendation"]).upper()
        # Only log actionable calls (BUY YES / BUY NO). NO TRADE rows are not
        # scored — they carry no directional position to resolve.
        if "BUY YES" not in rec and "BUY NO" not in rec:
            continue
        rows.append({
            "market": r["market"],
            "category": r["category"],
            "kalshi_ticker": r.get("kalshi_ticker") if pd.notna(r.get("kalshi_ticker")) else None,
            "report_date": report_date,
            "kalshi_price": float(r["kalshi_price"]),
            "afg_probability": float(r["afg_probability"]),
            "conviction": r["conviction"],
            "recommendation": "BUY YES" if "BUY YES" in rec else "BUY NO",
            "contract_close_date": r.get("contract_close_date") if pd.notna(r.get("contract_close_date")) else None,
        })

    if not rows:
        print("No actionable (BUY YES/BUY NO) calls to log this cycle.")
        return

    add_predictions_bulk(rows)
    missing = [r["market"] for r in rows if not r["kalshi_ticker"]]
    print(f"Logged {len(rows)} actionable calls for {report_date}.")
    if missing:
        print(f"  {len(missing)} logged without a ticker (won't auto-resolve until backfilled):")
        for m in missing:
            print(f"    - {m}")


if __name__ == "__main__":
    main()
