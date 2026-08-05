"""
db.py — SQLite replacement for the Airtable "AFG Predictions" + "AFG Performance" tables.

SQLite ships with Python (the `sqlite3` module is in the standard library) so
this costs nothing to run and needs no server, no account, and no monthly fee.
The whole database is a single file: afg_scorecard.db

Run this once to create the schema:
    python db.py
"""

import sqlite3
from contextlib import contextmanager

DB_PATH = "afg_scorecard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    market              TEXT NOT NULL,
    category            TEXT NOT NULL,       -- Sports / Economics / Politics / Crypto / Weather
    kalshi_ticker       TEXT,                 -- needed to poll resolution later
    report_date         TEXT NOT NULL,        -- ISO date, e.g. 2026-07-15
    kalshi_price        REAL NOT NULL,        -- implied probability, 0.0-1.0
    afg_probability     REAL NOT NULL,        -- 0.0-1.0
    edge_score          REAL NOT NULL,        -- afg_probability - kalshi_price
    conviction          TEXT NOT NULL,        -- HIGH / MEDIUM / SPECULATIVE
    recommendation      TEXT NOT NULL,        -- BUY YES / BUY NO / NO TRADE
    contract_close_date TEXT,                 -- ISO date, when the market resolves
    status              TEXT NOT NULL DEFAULT 'Open',  -- Open / Resolved
    outcome             INTEGER,              -- 1 = YES occurred, 0 = NO occurred, NULL until resolved
    brier_score         REAL,                 -- (afg_probability - outcome)^2
    kalshi_brier_score  REAL,                 -- (kalshi_price - outcome)^2, for AFG-vs-market comparison
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_status ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_category ON predictions(category);
CREATE INDEX IF NOT EXISTS idx_report_date ON predictions(report_date);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    print(f"Database ready at {DB_PATH}")


def add_prediction(market, category, kalshi_ticker, report_date, kalshi_price,
                    afg_probability, conviction, recommendation, contract_close_date):
    """Log a single call. Call this once per market, 25x per report."""
    edge_score = round(afg_probability - kalshi_price, 4)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO predictions
               (market, category, kalshi_ticker, report_date, kalshi_price,
                afg_probability, edge_score, conviction, recommendation, contract_close_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (market, category, kalshi_ticker, report_date, kalshi_price,
             afg_probability, edge_score, conviction, recommendation, contract_close_date),
        )


def add_predictions_bulk(rows):
    """
    rows: list of dicts with keys matching add_prediction's params.
    This is what you'll call once per MWF report — 25 dicts in, 25 rows logged.
    """
    with get_conn() as conn:
        for r in rows:
            edge_score = round(r["afg_probability"] - r["kalshi_price"], 4)
            conn.execute(
                """INSERT INTO predictions
                   (market, category, kalshi_ticker, report_date, kalshi_price,
                    afg_probability, edge_score, conviction, recommendation, contract_close_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r["market"], r["category"], r.get("kalshi_ticker"), r["report_date"],
                 r["kalshi_price"], r["afg_probability"], edge_score, r["conviction"],
                 r["recommendation"], r.get("contract_close_date")),
            )
    print(f"Logged {len(rows)} predictions for {rows[0]['report_date'] if rows else 'N/A'}")


def _parse_date(value):
    """
    Parses a stored close date into a datetime.date.

    The database has historically stored dates in two formats: ISO
    (2026-12-31) and US short form (12/31/2026). A plain SQL string
    comparison between these is unsafe -- "12/31/2026" <= "2026-08-05"
    evaluates TRUE because "1" sorts before "2", which caused markets
    closing in Oct/Nov/Dec to be treated as past due and falsely
    resolved. Dates are therefore parsed in Python, not compared as text.
    """
    import datetime
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def get_open_predictions_due(as_of_date):
    """
    Predictions still marked Open whose contract_close_date has genuinely
    passed. Dates are parsed rather than string-compared -- see _parse_date.
    """
    import datetime
    if isinstance(as_of_date, str):
        cutoff = _parse_date(as_of_date) or datetime.date.today()
    else:
        cutoff = as_of_date

    with get_conn() as conn:
        cur = conn.execute(
            """SELECT * FROM predictions
               WHERE status = 'Open' AND contract_close_date IS NOT NULL"""
        )
        rows = [dict(row) for row in cur.fetchall()]

    due = []
    for row in rows:
        close = _parse_date(row.get("contract_close_date"))
        if close is None:
            print(f"  WARNING: unparseable close date "
                  f"{row.get('contract_close_date')!r} for "
                  f"'{row.get('market')}' -- skipped.")
            continue
        if close <= cutoff:
            due.append(row)
    return due


def record_outcome(prediction_id, outcome):
    """
    outcome: 1 if YES occurred, 0 if NO occurred.
    Computes and stores both Brier scores, flips status to Resolved.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT afg_probability, kalshi_price FROM predictions WHERE id = ?",
                            (prediction_id,)).fetchone()
        if row is None:
            raise ValueError(f"No prediction with id {prediction_id}")
        afg_brier = (row["afg_probability"] - outcome) ** 2
        kalshi_brier = (row["kalshi_price"] - outcome) ** 2
        conn.execute(
            """UPDATE predictions
               SET outcome = ?, brier_score = ?, kalshi_brier_score = ?, status = 'Resolved'
               WHERE id = ?""",
            (outcome, afg_brier, kalshi_brier, prediction_id),
        )


def set_ticker(prediction_id, kalshi_ticker, contract_close_date=None):
    """
    Backfill a ticker (and optionally a close date) on a prediction that was
    logged without one. Once both are set, the row becomes eligible for
    resolve.py's automatic resolution checking.
    """
    with get_conn() as conn:
        if contract_close_date:
            conn.execute(
                "UPDATE predictions SET kalshi_ticker = ?, contract_close_date = ? WHERE id = ?",
                (kalshi_ticker, contract_close_date, prediction_id),
            )
        else:
            conn.execute(
                "UPDATE predictions SET kalshi_ticker = ? WHERE id = ?",
                (kalshi_ticker, prediction_id),
            )


def list_missing_tickers():
    """Show every logged prediction that still needs a ticker backfilled
    before it can be auto-resolved."""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT id, market, category, report_date FROM predictions "
            "WHERE kalshi_ticker IS NULL OR kalshi_ticker = '' ORDER BY id"
        )
        return [dict(row) for row in cur.fetchall()]


if __name__ == "__main__":
    init_db()
