"""
afg_logging_rules.py — the single source of truth for how AFG calls are
recorded in the scorecard database.

Used by:
  * 045_log_predictions.py   (every Mon/Wed/Fri cycle)
  * backfill_scorecard.py    (one-time replay of every published cycle)

Using one module for both guarantees past and future calls follow identical
rules.

RULES (applied per contract, in report-date order)
  1. FIRST CALL     The first BUY YES / BUY NO AFG publishes on a contract is
                    logged. This is what the First-Call track scores.
  2. REVERSAL       If AFG later publishes the opposite direction, that call is
                    logged too. The Updated-Position track and the Position
                    Changes table use it.
  3. CLOSURE        If AFG publishes NO TRADE on a contract it holds, the
                    position is marked closed as of that date. Closed positions
                    are excluded from the Updated-Position track but STILL score
                    on the First-Call track and appear in the Closed Positions
                    table.
  4. REOPEN         If AFG publishes a BUY call on a contract it had closed,
                    that call is logged and the position is open again.
  5. SAME DIRECTION Repeating an existing open call logs nothing new.
  6. RESOLVED       Contracts already resolved in the database are never
                    modified by these rules.
  7. VOID           Rows marked Void are ignored. If a contract exists only as
                    Void rows, nothing is inserted and a warning is printed,
                    because those rows were voided deliberately.
"""

import datetime

from db import _parse_date

# ── Ticker spellings that refer to the same Kalshi contract ──────────────────
# AFG reports used more than one spelling for several contracts. Every
# spelling on the left is stored as the spelling on the right so that one
# position is never split into two.
TICKER_ALIASES = {
    "KXCLARITY-28JAN01":         "KXCRYPTOSTRUCTURE-28JAN01",
    "KXCRYPTOSTRUCT-28JAN01":    "KXCRYPTOSTRUCTURE-28JAN01",
    "KXGTA6":                    "KXGTA6-B2027",
    "KXHORMUZNORM-26MAR17":      "KXHORMUZNORM-26MAR17-JAN27",
    "KXLEADERSOUT-26-BN":        "KXLEADERSOUT-27JAN01-BN",
    "KXBOND-30":                 "KXBOND-30-CT",
    "KXRECESSION-26":            "KXRECSSNBER-26",
    "KXALIENS-27":               "KXALIENS-27-JAN29",
    "KXUSAIRANAGREEMENT-27":     "KXUSAIRANAGREEMENT-27-JAN29",
    # Big Brother: Kalshi's real tickers use the first three letters of the name
    "KXBIGBROTHER-26DEC31-RD":   "KXBIGBROTHER-26DEC31-RIC",
    "KXBIGBROTHER-26DEC31-YP":   "KXBIGBROTHER-26DEC31-YAS",
    "KXBIGBROTHER-26DEC31-DC":   "KXBIGBROTHER-26DEC31-DRE",
    # First-hurricane names: Kalshi uses the first three letters of the name
    # (verified: KXFIRSTHURRICANE-26DEC01ATL-ISA, KXHURRICANENAMES-...-ART)
    "KXFIRSTHURRICANE-26DEC01ATL-FY":  "KXFIRSTHURRICANE-26DEC01ATL-FAY",
    "KXFIRSTHURRICANE-26DEC01ATL-GZ":  "KXFIRSTHURRICANE-26DEC01ATL-GON",
    "KXFIRSTHURRICANE-26DEC01ATL-HN":  "KXFIRSTHURRICANE-26DEC01ATL-HAN",
    "KXFIRSTHURRICANE-26DEC01ATL-IS":  "KXFIRSTHURRICANE-26DEC01ATL-ISA",
}


def canon(ticker):
    if ticker is None:
        return None
    t = str(ticker).strip()
    return TICKER_ALIASES.get(t, t)


def iso(value):
    d = _parse_date(value)
    return d.isoformat() if d else (str(value) if value else None)


def direction(rec):
    r = str(rec or "").upper()
    if "BUY YES" in r:
        return "BUY YES"
    if "BUY NO" in r:
        return "BUY NO"
    return "NO TRADE"


def ensure_columns(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()}
    if "afg_closed" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN afg_closed INTEGER DEFAULT 0")
    if "afg_closed_date" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN afg_closed_date TEXT")
    if "afg_closed_reason" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN afg_closed_reason TEXT")


def normalize_dates(conn):
    """Rewrite every report_date and contract_close_date in ISO form.
    Returns the number of rows changed."""
    changed = 0
    for rid, rd, cd in conn.execute(
        "SELECT id, report_date, contract_close_date FROM predictions"
    ).fetchall():
        new_rd, new_cd = iso(rd), iso(cd)
        if new_rd != rd or new_cd != cd:
            conn.execute(
                "UPDATE predictions SET report_date=?, contract_close_date=? WHERE id=?",
                (new_rd, new_cd, rid),
            )
            changed += 1
    return changed


def canonicalize_db_tickers(conn):
    """Rename any aliased ticker already stored in the database.
    Returns a list of (old, new, n_rows)."""
    renames = []
    for old, new in TICKER_ALIASES.items():
        n = conn.execute(
            "UPDATE predictions SET kalshi_ticker=? WHERE kalshi_ticker=?", (new, old)
        ).rowcount
        if n:
            renames.append((old, new, n))
    return renames


def _rows_for(conn, ticker):
    return conn.execute(
        "SELECT id, status, recommendation, report_date, "
        "COALESCE(afg_closed, 0) AS afg_closed FROM predictions WHERE kalshi_ticker=?",
        (ticker,),
    ).fetchall()


def _insert(conn, r, ticker, report_date):
    afg_p, kal_p = float(r["afg_probability"]), float(r["kalshi_price"])
    conn.execute(
        """INSERT INTO predictions
           (market, category, kalshi_ticker, report_date, kalshi_price,
            afg_probability, edge_score, conviction, recommendation,
            contract_close_date, status, afg_closed)
           VALUES (?,?,?,?,?,?,?,?,?,?, 'Open', 0)""",
        (r["market"], r["category"], ticker, report_date, kal_p, afg_p,
         round(afg_p - kal_p, 4), r["conviction"], direction(r["recommendation"]),
         iso(r.get("contract_close_date"))),
    )


def process_cycle(conn, report_date, rows, events):
    """Apply the logging rules to one published cycle.

    report_date : ISO date string of the cycle
    rows        : list of dicts (one per approved_predictions.csv row)
    events      : list; (kind, ticker, market, detail) tuples are appended
    """
    report_date = iso(report_date)
    for r in rows:
        ticker = canon(r.get("kalshi_ticker"))
        if not ticker or ticker.lower() == "nan":
            events.append(("warn", None, r.get("market"), "no ticker — not logged"))
            continue
        rec = direction(r.get("recommendation"))
        all_rows = _rows_for(conn, ticker)
        live = [x for x in all_rows if x["status"] != "Void"]

        if any(x["status"] == "Resolved" for x in live):
            continue  # rule 6

        if rec in ("BUY YES", "BUY NO"):
            if not live:
                if all_rows:  # only Void rows exist
                    events.append(("warn", ticker, r["market"],
                                   "exists only as Void rows — not logged"))
                    continue
                _insert(conn, r, ticker, report_date)
                events.append(("first", ticker, r["market"],
                               f"{report_date} {rec} @ {float(r['afg_probability']):.0%}"))
                continue

            latest = max(live, key=lambda x: _parse_date(x["report_date"]) or datetime.date.min)
            all_closed = all(x["afg_closed"] for x in live)

            if all_closed:
                _insert(conn, r, ticker, report_date)
                conn.execute(
                    "UPDATE predictions SET afg_closed=0, afg_closed_date=NULL, "
                    "afg_closed_reason=NULL WHERE kalshi_ticker=?", (ticker,))
                events.append(("reopen", ticker, r["market"],
                               f"{report_date} {rec} @ {float(r['afg_probability']):.0%}"))
            elif direction(latest["recommendation"]) != rec:
                _insert(conn, r, ticker, report_date)
                events.append(("reversal", ticker, r["market"],
                               f"{direction(latest['recommendation'])} -> {rec} on {report_date}"))
            # else rule 5: same direction, nothing new

        else:  # NO TRADE
            if live and not all(x["afg_closed"] for x in live):
                conn.execute(
                    "UPDATE predictions SET afg_closed=1, afg_closed_date=?, "
                    "afg_closed_reason=? WHERE kalshi_ticker=?",
                    (report_date, f"AFG published NO TRADE on {report_date}", ticker))
                events.append(("closed", ticker, r["market"], f"closed {report_date}"))
