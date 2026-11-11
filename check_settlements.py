"""
check_settlements.py  --  AFG settlement cross-check (added November 11th, 2026)
================================================================================
Compares every resolved outcome in afg_scorecard.db against Kalshi's own
settlement record. This is the check that would have caught the four wrong
outcomes found on November 11th (Alcaraz, hottest July, Dodgers, Isaias).

RULES
  1. Kalshi has settled the market (result = yes/no):
       the stored outcome MUST equal Kalshi's result. No exceptions, and an
       override row cannot change it.
  2. Kalshi has not settled yet (result blank):
       the outcome counts only if settlement_overrides.csv has a row for the
       ticker with the same outcome, an event date that has passed, and a
       source. Use this for outcomes that are already certain (a departure
       that happened, a title that was clinched).
  3. Neither Kalshi's live endpoint nor its historical archive has the
     ticker, or Kalshi cannot be reached:
       FAIL. Either the ticker in the database is wrong, or the check could
       not run -- both must be fixed before publishing. The check fails
       closed: no answer from Kalshi is never treated as a pass.
  4. Two active rows for one ticker with different outcomes: FAIL.

settlement_overrides.csv columns:
  ticker,outcome,event_date,source
  e.g. KXF1-26-KA,1,2026-11-01,https://www.aljazeera.com/sports/2026/11/2/...

USAGE (from C:\\Users\\qwhit\\AFG\\)
  python3 check_settlements.py        exit 0 = all outcomes match, 1 = stop
It also runs automatically as Check 13 in verify_afg.py and before every
06_build_scorecard.py build.
"""

import csv
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime

DB_PATH = "afg_scorecard.db"
OVERRIDES_PATH = "settlement_overrides.csv"
KALSHI_MARKET_URL = "https://api.elections.kalshi.com/trade-api/v2/markets/{}"
# Markets that settled before Kalshi's historical cutoff are removed from the
# live endpoint and served only from the archive (docs.kalshi.com, "Historical data").
KALSHI_HISTORICAL_URL = "https://api.elections.kalshi.com/trade-api/v2/historical/markets/{}"
ACTIVE = "status NOT IN ('Void','Superseded')"


class NotFound(Exception):
    pass


def _get_json(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "AFG-settlement-check",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_market(ticker, timeout=20):
    """Return Kalshi's market record for one ticker: the live endpoint first,
    then Kalshi's historical archive. Raises NotFound only if neither has it."""
    try:
        return _get_json(KALSHI_MARKET_URL.format(ticker), timeout).get("market", {})
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    try:
        data = _get_json(KALSHI_HISTORICAL_URL.format(ticker), timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotFound(ticker)
        raise
    market = data.get("market", data) if isinstance(data, dict) else {}
    market = dict(market)
    market["_source"] = "archive"
    return market


def _parse_date(val):
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None


def load_overrides(path=OVERRIDES_PATH):
    overrides, problems = {}, []
    if not os.path.exists(path):
        return overrides, problems
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            t = (row.get("ticker") or "").strip()
            if not t:
                continue
            out = (row.get("outcome") or "").strip()
            src = (row.get("source") or "").strip()
            ev = _parse_date(row.get("event_date"))
            if out not in ("0", "1") or not src or ev is None:
                problems.append(f"{path} line {i} ({t}): needs outcome 0/1, a valid event_date and a source")
                continue
            overrides[t] = {"outcome": int(out), "event_date": ev, "source": src}
    return overrides, problems


def check_settlements(db_path=DB_PATH, fetch=fetch_market, overrides_path=OVERRIDES_PATH,
                      today=None, pause=0.15, verbose=True):
    """Return (report_rows, problems). problems empty = safe to publish."""
    today = today or date.today()
    overrides, problems = load_overrides(overrides_path)
    report = []

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"SELECT ticker, outcome FROM predictions WHERE outcome IS NOT NULL AND outcome != '' "
                f"AND {ACTIVE} AND ticker IS NOT NULL AND ticker != '' ORDER BY ticker")
    stored = {}
    for ticker, out in cur.fetchall():
        stored.setdefault(ticker, set()).add(str(out).strip())
    conn.close()

    for ticker in sorted(stored):
        outs = stored[ticker]
        if len(outs) > 1 or not outs <= {"0", "1"}:
            problems.append(f"{ticker}: active rows disagree or are not 0/1 (stored {sorted(outs)})")
            report.append((ticker, "/".join(sorted(outs)), "-", "FAIL"))
            continue
        db_out = int(next(iter(outs)))

        try:
            m = fetch(ticker)
        except NotFound:
            problems.append(f"{ticker}: Kalshi has no market with this ticker -- the stored ticker is "
                            f"probably wrong; correct it before publishing")
            report.append((ticker, db_out, "not found", "FAIL"))
            continue
        except Exception as e:  # network, timeout, bad JSON: fail closed
            problems.append(f"{ticker}: could not reach Kalshi ({type(e).__name__}: {e}) -- check not run")
            report.append((ticker, db_out, "no answer", "FAIL"))
            continue
        finally:
            if pause:
                time.sleep(pause)

        result = str(m.get("result") or "").strip().lower()
        src = " (archive)" if m.get("_source") == "archive" else ""
        ov = overrides.get(ticker)

        if result in ("yes", "no"):
            k_out = 1 if result == "yes" else 0
            if k_out != db_out:
                problems.append(f"{ticker}: stored {db_out} but Kalshi settled {result.upper()} -- "
                                f"set outcome = {k_out}")
                report.append((ticker, db_out, f"settled {result}{src}", "FAIL"))
            elif ov and ov["outcome"] != k_out:
                problems.append(f"{ticker}: override says {ov['outcome']} but Kalshi settled "
                                f"{result.upper()} -- delete the override row")
                report.append((ticker, db_out, f"settled {result}{src}", "FAIL"))
            else:
                report.append((ticker, db_out, f"settled {result}{src}", "ok"))
        elif result == "":
            status = m.get("status", "?")
            if ov is None:
                problems.append(f"{ticker}: Kalshi has not settled it (status {status}) and there is no "
                                f"documented early resolution in {overrides_path} -- reopen it or add one")
                report.append((ticker, db_out, f"unsettled ({status})", "FAIL"))
            elif ov["outcome"] != db_out:
                problems.append(f"{ticker}: stored {db_out} but the override documents {ov['outcome']}")
                report.append((ticker, db_out, f"unsettled ({status})", "FAIL"))
            elif ov["event_date"] > today:
                problems.append(f"{ticker}: override event_date {ov['event_date']} is in the future")
                report.append((ticker, db_out, f"unsettled ({status})", "FAIL"))
            else:
                report.append((ticker, db_out, f"early: {ov['event_date']}", "ok"))
        else:
            problems.append(f"{ticker}: Kalshi result is '{result}' (not yes/no) -- score it by hand")
            report.append((ticker, db_out, f"result {result}", "FAIL"))

    if verbose:
        print(f"{'TICKER':<42} {'STORED':<7} {'KALSHI':<22} CHECK")
        print("-" * 80)
        for t, o, k, c in report:
            print(f"{t:<42} {str(o):<7} {k:<22} {c}")
        print("-" * 80)
        if problems:
            print(f"\nSTOP -- {len(problems)} problem(s):")
            for p in problems:
                print(f"  * {p}")
        else:
            print(f"\nAll {len(report)} resolved outcomes match Kalshi or a documented early resolution.")
    return report, problems


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        sys.exit(f"{DB_PATH} not found -- run from C:\\Users\\qwhit\\AFG\\")
    _, probs = check_settlements()
    sys.exit(1 if probs else 0)
