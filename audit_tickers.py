"""
audit_tickers.py — READ-ONLY check of every contract code in afg_scorecard.db
against Kalshi's public API.

WHY: some calls were stored under contract codes that do not exist on Kalshi
(e.g. KXBOND-30-CT for Callum Turner; Kalshi's code is KXBOND-30-CAL).
05_update_scorecard.py looks each code up on Kalshi, so a wrong code errors
quietly and the call never scores. A Claude audit on 12 Oct 2026 proposed a
correct code for each mismatch (PROPOSED below). This script checks those
proposals directly against Kalshi's raw API — no summaries, no guessing —
so we can review the evidence before anything in the database changes.

It also tries Kalshi's /historical/ endpoint, because older settled markets
are only served there and the live lookup fails for them even when the code
is right.

NOTHING IS WRITTEN. The database is opened read-only. The output is printed
and saved to reports/ticker_audit_<today>.txt — paste that file into chat.

Run from C:\\Users\\qwhit\\AFG:
    python3 audit_tickers.py
"""

import datetime
import os
import sqlite3
import time

import requests

import db

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Stored code -> proposed Kalshi code(s). Every proposal is checked below;
# none is applied by this script.
PROPOSED = {
    "KXAGCOMMITTEE-26OCT01":        ["KXBLANCHEJUDICIARY-27-26OCT01"],
    "KXALIENS-27-JAN29":            ["KXALIENS-27-29"],
    "KXATP-26USO-CA":               ["KXATP-26USO-ALC"],
    "KXBIGBROTHER-26DEC31-DV":      ["KXBIGBROTHER-26DEC31-DEE"],
    "KXBOND-30-CT":                 ["KXBOND-30-CAL"],
    "KXBOND-30-JB":                 ["KXBOND-30-JACK"],
    "KXBOND-30-JL":                 ["KXBOND-30-JAC"],
    "KXCRYPTOSTRUCTURE-28JAN01":    ["KXCRYPTOSTRUCTURE-27JAN-28"],
    "KXDWTS-35-EF":                 ["KXDANCINGWITHTHESTARS-26DEC31-EFRE"],
    "KXF1-26-ANT":                  ["KXF1-26-KA"],
    "KXFEDHIKE-B2027":              ["FEDHIKE-26DEC31", "KXFEDHIKE-2-26DEC31"],
    "KXGAMEAWARDS-2026":            ["KXGAMEAWARDS-2026-GTA"],
    "KXGTA6-B2027":                 ["GTA6-26DEC31"],
    "KXGTEMP-26":                   ["KXGTEMP-26-P0", "KXGTEMP-27-P0"],
    "KXHEISMAN-27-DM":              ["KXHEISMAN-27-DMENS"],
    "KXHEISMAN-27-JS":              ["KXHEISMAN-27-JSMIT"],
    "KXHEISMAN-27-TC":              ["KXHEISMAN-27-TCHAM"],
    "KXHIGHJULY-26":                ["KXHMONTH-26JUL"],
    "KXHORMUZNORM-26MAR17-APR27":   ["KXHORMUZNORM-26MAR17-B270401"],
    "KXHORMUZNORM-26MAR17-DEC26":   ["KXHORMUZNORM-26MAR17-B261201"],
    "KXHORMUZNORM-26MAR17-JAN27":   ["KXHORMUZNORM-26MAR17-B270101"],
    "KXHORMUZNORM-26MAR17-JAN28":   ["KXHORMUZNORM-26MAR17-B280101"],
    "KXHORMUZNORM-26MAR17-JUL27":   ["KXHORMUZNORM-26MAR17-B270701"],
    "KXHURCHI-26":                  ["KXHURPATHHAWAII-26DEC"],
    "KXLEADERSOUT-27JAN01-BN":      ["KXLEADERSOUT-27JAN01-BNETISR"],
    "KXLEADERSOUT-27JAN01-CL":      ["KXLEADERSOUT-27JAN01-PLUXPMNZ"],
    "KXNEXTAG-29-TB":               ["KXNEXTAG-29-TBLA"],
    "KXOSCARPIC-27":                ["KXOSCARPIC-27-ODY"],
    "KXPGATOUR-3MO26-SCH":          ["KXPGATOUR-3MO26-SSCH"],
    "KXPGATOUR-BMW26-SS":           ["KXPGATOUR-BMC26-SSCH"],
    "KXPGATOUR-FESJC26-SS":         ["KXPGATOUR-FESJC26-SSCH"],
    "KXPGATOUR-TOC26-SS":           ["KXPGATOUR-TOC26-SSCH"],
    "KXQUAKEWORLD-26SEP01-78":      ["KXEARTHQUAKEM-26AUG-78"],
    "KXRATECUTCOUNT-26DEC31":       ["KXRATECUTCOUNT-26DEC31-T0"],
    "KXSAVEACT-27":                 ["KXSAVEACT-27-JAN04"],
    "KXUSAIRANAGREEMENT-27-JAN29":  ["KXUSAIRANAGREEMENT-27-28", "KXUSAIRANAGREEMENT-27-29JAN20"],
}

_cache = {}


def fetch(ticker):
    """Return (source, market_dict) or (None, error_text). Tries the live
    endpoint, then /historical/."""
    if ticker in _cache:
        return _cache[ticker]
    out = (None, "not found on live or historical endpoint")
    for source, path in (("live", f"/markets/{ticker}"),
                         ("historical", f"/historical/markets/{ticker}")):
        try:
            r = requests.get(BASE + path, timeout=20)
        except Exception as e:  # network problem: report, don't guess
            out = (None, f"network error: {e}")
            break
        if r.status_code == 200:
            m = r.json().get("market") or {}
            if m.get("ticker"):
                out = (source, m)
                break
        time.sleep(0.15)
    _cache[ticker] = out
    return out


def describe(ticker):
    source, m = fetch(ticker)
    if source is None:
        return False, f"NOT FOUND ({m})"
    title = (m.get("title") or "").strip()
    sub = (m.get("yes_sub_title") or "").strip()
    status = m.get("status") or ""
    result = m.get("result") or ""
    settled = (m.get("settlement_ts") or m.get("expiration_time") or "")[:10]
    txt = f'{status}{"/" + result if result else ""}  "{title}" [{sub}]'
    if result:
        txt += f"  settled {settled}"
    txt += f"  ({source})"
    return True, txt


def main():
    today = datetime.date.today().isoformat()
    con = sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT kalshi_ticker AS t, market, status, outcome, recommendation, "
        "report_date, COALESCE(afg_closed,0) AS closed FROM predictions "
        "WHERE status NOT IN ('Void','Superseded') AND kalshi_ticker IS NOT NULL "
        "ORDER BY kalshi_ticker, report_date").fetchall()
    con.close()

    by_t = {}
    for r in rows:
        by_t.setdefault(r["t"], []).append(r)

    lines, flags = [], []
    lines.append(f"AFG TICKER AUDIT — {today} — {len(by_t)} contract codes, {len(rows)} rows (read-only)")
    lines.append("=" * 100)
    for t, rs in sorted(by_t.items()):
        statuses = ", ".join(sorted({r["status"] for r in rs}))
        res = [r for r in rs if r["status"] == "Resolved"]
        db_out = ""
        if res:
            db_out = " outcome=" + ("YES" if res[0]["outcome"] == 1 else "NO")
        first = rs[0]
        lines.append("")
        lines.append(f"{t}   [DB: {len(rs)} row(s), {statuses}{db_out}; first {first['report_date']} "
                     f"{first['recommendation']}] {first['market']}")
        ok, txt = describe(t)
        lines.append(f"    stored code   : {txt}")
        candidates = PROPOSED.get(t, [])
        for c in candidates:
            ok2, txt2 = describe(c)
            lines.append(f"    proposed code : {c}  ->  {txt2}")
        # flags
        if not ok and not candidates:
            flags.append(f"{t}: stored code not on Kalshi and no proposal")
        if not ok and candidates:
            flags.append(f"{t}: stored code not on Kalshi -> review proposal {candidates}")
        if ok and candidates:
            flags.append(f"{t}: stored code EXISTS on Kalshi but a correction was proposed — check which matches the call")
        for c in candidates:
            csrc, cm = fetch(c)
            if csrc is None:
                continue
            cres = cm.get("result") or ""
            if cres not in ("yes", "no"):
                continue
            if res and (cres == "yes") != (res[0]["outcome"] == 1):
                flags.append(f"{t}: DB outcome differs from Kalshi result on {c} ({cres.upper()})")
            if not res:
                flags.append(f"{t}: still Open in DB, but {c} settled {cres.upper()} — this call is missing from the scorecard")
        if ok:
            src, m = fetch(t)
            kres = m.get("result") or ""
            if res and kres in ("yes", "no") and (kres == "yes") != (res[0]["outcome"] == 1):
                flags.append(f"{t}: DB outcome differs from Kalshi result ({kres})")
            if not res and kres in ("yes", "no"):
                flags.append(f"{t}: Kalshi settled {kres.upper()} but DB row is still Open")
            if src == "historical" and not res:
                flags.append(f"{t}: only on /historical/ — 05_update_scorecard.py cannot see it yet")

    lines.append("")
    lines.append("=" * 100)
    lines.append(f"FLAGS ({len(flags)})")
    lines.extend("  - " + f for f in flags)
    out = "\n".join(lines)
    print(out)
    os.makedirs("reports", exist_ok=True)
    path = f"reports/ticker_audit_{today}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(f"\nSaved to {path} — paste this file into chat. Nothing in the database was changed.")


if __name__ == "__main__":
    main()
