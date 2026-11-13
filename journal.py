"""
journal.py  --  AFG prediction journal (added November 12th, 2026)
================================================================================
Superforecaster Commandment 8: write down the facts and reasoning AT FORECAST
TIME, so hindsight bias cannot rewrite them later.

Every cycle, each call in data\\approved_predictions.csv is copied into the
`call_journal` table of afg_scorecard.db together with three reasoning fields:

    outside_view     the base rate / comparison class the estimate started from
    rationale        the evidence that moved it, with the source and its date
    counterargument  the strongest case against the call

RULES
  * Append-only. A (report_date, ticker) pair is written once and never
    modified, so the journal is a faithful record of what AFG believed then.
  * Every BUY YES / BUY NO row must have all three fields filled in (at least
    15 characters each). Otherwise the journal STOPS the cycle -- a call that
    cannot be explained is not logged.
  * NO TRADE rows are journaled too (reasoning optional but kept if present).
  * Never touches the predictions table, so it cannot affect the scorecard.

Run from C:\\Users\\qwhit\\AFG\\ (run_cycle.py does this automatically):
    python3 journal.py
"""
import csv
import datetime as dt
import os
import sqlite3
import sys

DB = "afg_scorecard.db"
CSV_PATH = "data/approved_predictions.csv"
REASONING = ("outside_view", "rationale", "counterargument")
MIN_LEN = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS call_journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date     TEXT NOT NULL,
    kalshi_ticker   TEXT NOT NULL,
    market          TEXT,
    category        TEXT,
    recommendation  TEXT,
    afg_probability REAL,
    kalshi_price    REAL,
    conviction      TEXT,
    outside_view    TEXT,
    rationale       TEXT,
    counterargument TEXT,
    logged_at       TEXT,
    UNIQUE (report_date, kalshi_ticker)
)"""


def _canon(ticker):
    try:
        from afg_logging_rules import canon
        return canon(ticker)
    except Exception:
        return (ticker or "").strip()


def _direction(rec):
    r = str(rec or "").upper()
    return "BUY YES" if "BUY YES" in r else "BUY NO" if "BUY NO" in r else "NO TRADE"


def log_journal(db=DB, csv_path=CSV_PATH, today=None, verbose=True, dry_run=False):
    """Returns (inserted, already_logged, problems). problems empty = ok.
    dry_run=True validates the file and writes nothing (used by run_cycle pre-flight)."""
    today = today or dt.date.today()
    problems = []
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        rows = list(reader)

    missing = [c for c in REASONING if c not in cols]
    if missing:
        msg = f"approved_predictions.csv has no column(s): {', '.join(missing)}"
        if verbose:
            print(f"JOURNAL STOPPED -- {msg}")
        return 0, 0, [msg]

    clean = []
    for i, r in enumerate(rows, start=2):
        t = _canon(r.get("kalshi_ticker"))
        d = (r.get("report_date") or "").strip()
        try:
            day = dt.date.fromisoformat(d)
        except ValueError:
            problems.append(f"line {i} ({t or '?'}): report_date '{d}' is not YYYY-MM-DD")
            continue
        if day > today:
            problems.append(f"line {i} ({t}): report_date {d} is in the future")
            continue
        if not t or t.lower() == "nan":
            problems.append(f"line {i}: no kalshi_ticker")
            continue
        rec = _direction(r.get("recommendation"))
        if rec != "NO TRADE":
            weak = [c for c in REASONING if len((r.get(c) or "").strip()) < MIN_LEN]
            if weak:
                problems.append(f"{t}: {rec} has empty or too-short {', '.join(weak)}")
                continue
        clean.append((day.isoformat(), t, r, rec))

    if problems:
        if verbose:
            print(f"JOURNAL STOPPED -- {len(problems)} problem(s); nothing was written:")
            for p in problems:
                print(f"  * {p}")
        return 0, 0, problems

    if dry_run:
        return 0, 0, []

    conn = sqlite3.connect(db)
    conn.execute(SCHEMA)
    inserted = already = 0
    now = dt.datetime.now().isoformat(timespec="seconds")
    for day, t, r, rec in clean:
        cur = conn.execute(
            "INSERT OR IGNORE INTO call_journal (report_date, kalshi_ticker, market, category, "
            "recommendation, afg_probability, kalshi_price, conviction, outside_view, rationale, "
            "counterargument, logged_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (day, t, r.get("market"), r.get("category"), rec,
             float(r["afg_probability"]), float(r["kalshi_price"]), r.get("conviction"),
             (r.get("outside_view") or "").strip(), (r.get("rationale") or "").strip(),
             (r.get("counterargument") or "").strip(), now))
        if cur.rowcount:
            inserted += 1
        else:
            already += 1
    conn.commit()
    conn.close()
    if verbose:
        print(f"  journal: {inserted} call(s) written, {already} already on file "
              f"(existing entries are never altered)")
    return inserted, already, []


if __name__ == "__main__":
    for p in (DB, CSV_PATH):
        if not os.path.exists(p):
            sys.exit(f"{p} not found -- run from C:\\Users\\qwhit\\AFG\\")
    _, _, probs = log_journal()
    sys.exit(1 if probs else 0)
