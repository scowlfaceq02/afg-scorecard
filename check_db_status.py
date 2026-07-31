"""
check_db_status.py — shows all Resolved and Void rows in the database.
Run: python3 check_db_status.py
"""
from db import get_conn

with get_conn() as conn:
    rows = conn.execute(
        "SELECT id, kalshi_ticker, status, outcome, report_date "
        "FROM predictions "
        "WHERE status IN ('Resolved', 'Void') "
        "ORDER BY status, id"
    ).fetchall()

if not rows:
    print("No Resolved or Void rows found.")
else:
    print(f"{'ID':<6} {'Status':<10} {'Outcome':<10} {'Date':<12} Ticker")
    print("-" * 70)
    for r in rows:
        print(f"{r[0]:<6} {r[2]:<10} {str(r[3]):<10} {str(r[4]):<12} {r[1]}")
