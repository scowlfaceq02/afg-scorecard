"""
AFG Database Migration Script
Adds missing columns (ticker, close_date, published_date) to afg_scorecard.db
and optionally seeds from approved_predictions.csv.

Run from C:\\Users\\qwhit\\AFG\\:
    python3 migrate_db.py
"""

import sqlite3
import csv
import os
from pathlib import Path

DB_PATH  = "afg_scorecard.db"
CSV_PATH = "data/approved_predictions.csv"

# ── 1. Connect ────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# ── 2. Show current schema ────────────────────────────────────────────────────
cur.execute("PRAGMA table_info(predictions)")
existing = {row[1] for row in cur.fetchall()}
print(f"Existing columns: {sorted(existing)}")

# ── 3. Add missing columns ────────────────────────────────────────────────────
REQUIRED = {
    "ticker":          "TEXT",
    "close_date":      "TEXT",
    "published_date":  "TEXT",
    # Other columns verify_afg.py expects — add if absent
    "category":        "TEXT",
    "kalshi_price":    "REAL",
    "afg_probability": "REAL",
    "conviction":      "TEXT",
    "recommendation":  "TEXT",
    "market":          "TEXT",
    "edge_score":      "REAL",
    "rationale":       "TEXT",
    "resolved":        "INTEGER DEFAULT 0",
    "outcome":         "TEXT",
    "resolution_date": "TEXT",
}

added = []
for col, dtype in REQUIRED.items():
    if col not in existing:
        cur.execute(f"ALTER TABLE predictions ADD COLUMN {col} {dtype}")
        added.append(col)
        print(f"  + Added column: {col} ({dtype})")

if not added:
    print("  All required columns already present — no schema changes needed.")

conn.commit()

# ── 4. Seed from CSV if table is empty ───────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM predictions")
row_count = cur.fetchone()[0]

if row_count == 0 and os.path.exists(CSV_PATH):
    print(f"\nTable is empty. Seeding from {CSV_PATH}...")
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows_inserted = 0
        for row in reader:
            # Map CSV columns → DB columns
            cur.execute("""
                INSERT INTO predictions
                    (market, category, ticker, published_date, kalshi_price,
                     afg_probability, conviction, recommendation, close_date,
                     edge_score, resolved)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                row.get("market", ""),
                row.get("category", ""),
                row.get("kalshi_ticker", ""),
                row.get("report_date", ""),
                float(row.get("kalshi_price", 0)),
                float(row.get("afg_probability", 0)),
                row.get("conviction", ""),
                row.get("recommendation", ""),
                row.get("contract_close_date", ""),
                round(float(row.get("afg_probability", 0)) - float(row.get("kalshi_price", 0)), 4),
            ))
            rows_inserted += 1
    conn.commit()
    print(f"  Inserted {rows_inserted} rows from CSV.")
elif row_count > 0:
    print(f"\nTable already has {row_count} rows — skipping seed.")
else:
    print(f"\nNo CSV found at {CSV_PATH} — skipping seed.")

# ── 5. Final check ────────────────────────────────────────────────────────────
cur.execute("PRAGMA table_info(predictions)")
final_cols = sorted(row[1] for row in cur.fetchall())
print(f"\nFinal columns: {final_cols}")

cur.execute("SELECT COUNT(*) FROM predictions")
print(f"Total rows:    {cur.fetchone()[0]}")

conn.close()
print("\nMigration complete. Run verify_afg.py to confirm.")
