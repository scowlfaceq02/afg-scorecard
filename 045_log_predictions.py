"""
045_log_predictions.py — records this cycle's published calls in the
scorecard database. Run after 04_build_report.py every Mon/Wed/Fri.

Rules live in afg_logging_rules.py and are shared with backfill_scorecard.py:
  first call logged; reversals logged; NO TRADE on a held contract closes it;
  a BUY call on a closed contract reopens it; resolved contracts untouched.

Run:
    python3 045_log_predictions.py
"""

import os
import sys
import sqlite3

import pandas as pd

import db
from afg_logging_rules import (ensure_columns, normalize_dates, process_cycle,
                               canonicalize_db_tickers)

APPROVED_CSV = "data/approved_predictions.csv"


def main():
    if not os.path.exists(APPROVED_CSV):
        print(f"ERROR: {APPROVED_CSV} not found. Run 04_build_report.py first.")
        sys.exit(1)
    df = pd.read_csv(APPROVED_CSV)
    if df.empty:
        print("No rows in approved_predictions.csv.")
        return
    report_date = str(df.iloc[0]["report_date"])

    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_columns(conn)
    normalize_dates(conn)
    for old, new, n in canonicalize_db_tickers(conn):
        print(f"  Ticker corrected: {old} -> {new} ({n} row(s))")
    events = []
    process_cycle(conn, report_date, df.to_dict("records"), events)
    conn.commit()
    conn.close()

    labels = {"first": "New call logged", "reversal": "Reversal logged",
              "closed": "Position closed", "reopen": "Position reopened", "warn": "WARNING"}
    if not events:
        print(f"{report_date}: no changes (all calls already recorded).")
        return
    print(f"{report_date}:")
    for kind, t, m, d in events:
        print(f"  {labels.get(kind, kind):18s} {str(t):34s} {d}")


if __name__ == "__main__":
    main()
