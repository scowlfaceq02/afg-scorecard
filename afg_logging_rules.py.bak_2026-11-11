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
  8. SUPERSEDED     Rows set aside by the backfill (status 'Superseded') are
                    invisible to these rules and to the scorecard, but kept in
                    the database for audit.
  7. VOID           Rows marked Void (duplicate copies removed in July 2026)
                    are invisible to these rules and never block logging.
"""

import datetime

from db import _parse_date

# ── Ticker spellings → the real Kalshi contract code ─────────────────────────
# AFG reports used more than one spelling for several contracts, and some
# spellings were never real Kalshi codes. Every spelling on the left is stored
# as the Kalshi code on the right, so one position is never split in two and
# 05_update_scorecard.py can look every call up on Kalshi.
#
# Every target below was verified against Kalshi's raw API by audit_tickers.py
# on 12 Oct 2026 (title and outcome matched the call's description).
# Each left-hand spelling maps DIRECTLY to its final code (no chains).
TICKER_ALIASES = {
    # Crypto market structure (Clarity Act), before Jan 1 2028
    "KXCLARITY-28JAN01":               "KXCRYPTOSTRUCTURE-27JAN-28",
    "KXCRYPTOSTRUCT-28JAN01":          "KXCRYPTOSTRUCTURE-27JAN-28",
    "KXCRYPTOSTRUCTURE-28JAN01":       "KXCRYPTOSTRUCTURE-27JAN-28",
    # GTA VI released before 2027 (Kalshi's code has no KX prefix)
    "KXGTA6":                          "GTA6-26DEC31",
    "KXGTA6-B2027":                    "GTA6-26DEC31",
    # Hormuz: Kalshi strike codes are B<yymmdd>
    "KXHORMUZNORM-26MAR17":            "KXHORMUZNORM-26MAR17-B270101",
    "KXHORMUZNORM-26MAR17-JAN27":      "KXHORMUZNORM-26MAR17-B270101",
    "KXHORMUZNORM-26MAR17-DEC26":      "KXHORMUZNORM-26MAR17-B261201",
    "KXHORMUZNORM-26MAR17-APR27":      "KXHORMUZNORM-26MAR17-B270401",
    "KXHORMUZNORM-26MAR17-JUL27":      "KXHORMUZNORM-26MAR17-B270701",
    "KXHORMUZNORM-26MAR17-JAN28":      "KXHORMUZNORM-26MAR17-B280101",
    # Leaders leaving office before Jan 1 2027
    "KXLEADERSOUT-26-BN":              "KXLEADERSOUT-27JAN01-BNETISR",
    "KXLEADERSOUT-27JAN01-BN":         "KXLEADERSOUT-27JAN01-BNETISR",
    "KXLEADERSOUT-27JAN01-CL":         "KXLEADERSOUT-27JAN01-PLUXPMNZ",
    # Next James Bond
    "KXBOND-30":                       "KXBOND-30-CAL",
    "KXBOND-30-CT":                    "KXBOND-30-CAL",
    "KXBOND-30-JL":                    "KXBOND-30-JAC",
    "KXBOND-30-JB":                    "KXBOND-30-JACK",
    "KXRECESSION-26":                  "KXRECSSNBER-26",
    # US confirms aliens exist, before Jan 20 2029
    "KXALIENS-27":                     "KXALIENS-27-29",
    "KXALIENS-27-JAN29":               "KXALIENS-27-29",
    # US-Iran nuclear deal: TWO different strikes. The 21 July 2026 call was
    # on "before Jan 1, 2028" (KXUSAIRANAGREEMENT-27-28); every later call was
    # on "before Jan 20, 2029". The bare code KXUSAIRANAGREEMENT-27 was used
    # for both strikes in July, so it is deliberately NOT aliased (corrected
    # by hand in afg_backfill_history.csv on 12 Oct 2026).
    "KXUSAIRANAGREEMENT-27-JAN29":     "KXUSAIRANAGREEMENT-27-29JAN20",
    # Big Brother: Kalshi uses the first three letters of the name
    "KXBIGBROTHER-26DEC31-RD":         "KXBIGBROTHER-26DEC31-RIC",
    "KXBIGBROTHER-26DEC31-YP":         "KXBIGBROTHER-26DEC31-YAS",
    "KXBIGBROTHER-26DEC31-DC":         "KXBIGBROTHER-26DEC31-DRE",
    "KXBIGBROTHER-26DEC31-DV":         "KXBIGBROTHER-26DEC31-DEE",
    # First-hurricane names: Kalshi uses the first three letters of the name
    "KXFIRSTHURRICANE-26DEC01ATL-FY":  "KXFIRSTHURRICANE-26DEC01ATL-FAY",
    "KXFIRSTHURRICANE-26DEC01ATL-GZ":  "KXFIRSTHURRICANE-26DEC01ATL-GON",
    "KXFIRSTHURRICANE-26DEC01ATL-HN":  "KXFIRSTHURRICANE-26DEC01ATL-HAN",
    "KXFIRSTHURRICANE-26DEC01ATL-IS":  "KXFIRSTHURRICANE-26DEC01ATL-ISA",
    # Major-hurricane count: Kalshi's strike suffix is T<n>
    "KXHURCTOTMAJ-26DEC01-0":          "KXHURCTOTMAJ-26DEC01-T0",
    "KXHURCTOTMAJ-26DEC01-1":          "KXHURCTOTMAJ-26DEC01-T1",
    # Blanche AG nomination reported out of Judiciary before Oct 1 2026
    "KXAGCOMMITTEE-26OCT01":           "KXBLANCHEJUDICIARY-27-26OCT01",
    "KXATP-26USO-CA":                  "KXATP-26USO-ALC",
    "KXDWTS-35-EF":                    "KXDANCINGWITHTHESTARS-26DEC31-EFRE",
    "KXF1-26-ANT":                     "KXF1-26-KA",
    # Fed hike by Dec 31 2026 (the market live in July; no KX prefix)
    "KXFEDHIKE-B2027":                 "FEDHIKE-26DEC31",
    "KXGAMEAWARDS-2026":               "KXGAMEAWARDS-2026-GTA",
    # Hottest year: KXGTEMP-26 is the event; its one market is -P0
    "KXGTEMP-26":                      "KXGTEMP-26-P0",
    "KXHEISMAN-27-DM":                 "KXHEISMAN-27-DMENS",
    "KXHEISMAN-27-JS":                 "KXHEISMAN-27-JSMIT",
    "KXHEISMAN-27-TC":                 "KXHEISMAN-27-TCHAM",
    "KXHIGHJULY-26":                   "KXHMONTH-26JUL",
    "KXHURCHI-26":                     "KXHURPATHHAWAII-26DEC",
    "KXNEXTAG-29-TB":                  "KXNEXTAG-29-TBLA",
    "KXOSCARPIC-27":                   "KXOSCARPIC-27-ODY",
    # Golf: four-letter player codes; the BMW Championship event is BMC26
    "KXPGATOUR-3MO26-SCH":             "KXPGATOUR-3MO26-SSCH",
    "KXPGATOUR-BMW26-SS":              "KXPGATOUR-BMC26-SSCH",
    "KXPGATOUR-FESJC26-SS":            "KXPGATOUR-FESJC26-SSCH",
    "KXPGATOUR-TOC26-SS":              "KXPGATOUR-TOC26-SSCH",
    "KXQUAKEWORLD-26SEP01-78":         "KXEARTHQUAKEM-26AUG-78",
    "KXRATECUTCOUNT-26DEC31":          "KXRATECUTCOUNT-26DEC31-T0",
    "KXSAVEACT-27":                    "KXSAVEACT-27-JAN04",
    # Verified against Kalshi's API on 16 Oct 2026. These spellings were only
    # ever used on NO TRADE rows (never logged), so no scored call is affected.
    "KXLAYOFFSYINFO-26":               "KXLAYOFFSYINFO-26-494000",
    "KXTRUMPADMINLEAVE-26-DCOL":       "KXTRUMPADMINLEAVE-26DEC31-DCOL",
    "KXTRUMPADMINLEAVE-26-PHEG":       "KXTRUMPADMINLEAVE-26DEC31-PHEG",
}

# No target may itself be a left-hand spelling (that would need two passes).
assert not set(TICKER_ALIASES.values()) & set(TICKER_ALIASES), "alias chain"


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
        "COALESCE(afg_closed, 0) AS afg_closed FROM predictions "
        "WHERE kalshi_ticker=? AND status NOT IN ('Superseded', 'Void')",
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
