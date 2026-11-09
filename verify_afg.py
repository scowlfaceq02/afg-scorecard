"""
verify_afg.py  —  AFG Pre-Publication Integrity Checker
12 checks before every Monday / Wednesday / Friday cycle

CHANGE LOG:
  November 9th, 2026 — Added checks 10, 11, 12 following full audit
  that found 74.1% reported accuracy was actually 59.3% due to:
    (a) outcome stored as 0/1 integer but parsed as YES/NO string
        → silent wrong scoring on every position (Check 10)
    (b) duplicate resolved rows inflating denominator (Check 11)
    (c) no independent cross-check before publish (Check 12)
  Check 12 now prints the verified accuracy number every cycle.
  Any discrepancy between Check 12 and 06_build_scorecard.py output
  MUST be resolved before publishing — the two numbers must match.

  November 6th, 2026 — Removed "first-call-only deduplication" check.
  Replaced with "final-call scoring compliance" check.
  Bayesian position updates (changing BUY NO → BUY YES) are correct
  behavior and must NOT be flagged as database errors.

USAGE:
  cd C:\\Users\\qwhit\\AFG
  python3 verify_afg.py

EXIT CODES:
  0 = all 12 checks passed — safe to run the cycle
  1 = one or more checks failed — fix before publishing
"""

import sqlite3
import os
import sys
from datetime import date, datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB_PATH    = "afg_scorecard.db"
LOG_PATH   = "logs/verify_afg.log"
PASS       = "✓ PASS"
FAIL       = "✗ FAIL"
WARN       = "⚠ WARN"
TODAY      = date.today()
TODAY_STR  = TODAY.isoformat()

results    = []
exit_code  = 0


def check(name, passed, detail=""):
    global exit_code
    status = PASS if passed else FAIL
    if not passed:
        exit_code = 1
    results.append((status, name, detail))
    print(f"  {status}  {name}" + (f"\n         → {detail}" if detail else ""))


def warn(name, detail=""):
    results.append((WARN, name, detail))
    print(f"  {WARN}  {name}" + (f"\n         → {detail}" if detail else ""))


def _parse_date(val):
    if val is None:
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


# ── CONNECT ───────────────────────────────────────────────────────────────────

print(f"\n{'='*62}")
print(f"AFG PRE-PUBLICATION INTEGRITY CHECK — {TODAY_STR}")
print(f"{'='*62}\n")

if not os.path.exists(DB_PATH):
    print(f"FATAL: {DB_PATH} not found. Run from C:\\Users\\qwhit\\AFG\\")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()


# ── CHECK 1: DATABASE CONNECTIVITY & SCHEMA ───────────────────────────────────
print("CHECK 1: Database connectivity and schema")
try:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    required = {"predictions"}
    missing  = required - set(tables)
    check(
        "Database accessible with required tables",
        len(missing) == 0,
        f"Missing tables: {missing}" if missing else f"Tables found: {', '.join(tables)}"
    )
except Exception as e:
    check("Database accessible with required tables", False, str(e))


# ── CHECK 2: REQUIRED COLUMNS PRESENT ────────────────────────────────────────
print("\nCHECK 2: Required columns in predictions table")
try:
    cur.execute("PRAGMA table_info(predictions)")
    cols = {r[1] for r in cur.fetchall()}
    required_cols = {
        "ticker", "market", "category", "recommendation",
        "afg_probability", "kalshi_price", "published_date",
        "outcome", "close_date", "status"
    }
    missing_cols = required_cols - cols
    check(
        "All required columns present",
        len(missing_cols) == 0,
        f"Missing: {missing_cols}" if missing_cols else f"{len(cols)} columns verified"
    )
except Exception as e:
    check("All required columns present", False, str(e))


# ── CHECK 3: NO NULL TICKERS OR CATEGORIES IN OPEN POSITIONS ─────────────────
print("\nCHECK 3: Open positions have ticker and category")
try:
    cur.execute("""
        SELECT COUNT(*) FROM predictions
        WHERE (ticker IS NULL OR ticker = '' OR category IS NULL OR category = '')
        AND (outcome IS NULL OR outcome = '')
        AND status NOT IN ('Void', 'Superseded')
    """)
    n_null = cur.fetchone()[0]
    check(
        "No open positions missing ticker or category",
        n_null == 0,
        f"{n_null} rows missing ticker/category — fix before publishing" if n_null else "All open positions have ticker and category"
    )
except Exception as e:
    check("No open positions missing ticker or category", False, str(e))


# ── CHECK 4: PROBABILITIES IN VALID RANGE ─────────────────────────────────────
print("\nCHECK 4: AFG and Kalshi probabilities in valid range")
try:
    cur.execute("""
        SELECT ticker, afg_probability, kalshi_price, published_date
        FROM predictions
        WHERE status NOT IN ('Void', 'Superseded')
        AND recommendation IN ('BUY YES', 'BUY NO')
    """)
    rows = cur.fetchall()
    bad  = []
    for ticker, afg_p, kal_p, pub in rows:
        try:
            a = float(afg_p)
            k = float(kal_p)
            # Accept both 0.0–1.0 and 0–100 ranges
            a_norm = a if a <= 1.0 else a / 100.0
            k_norm = k if k <= 1.0 else k / 100.0
            if not (0.0 <= a_norm <= 1.0):
                bad.append(f"{ticker} AFG={afg_p}")
            if not (0.0 <= k_norm <= 1.0):
                bad.append(f"{ticker} Kalshi={kal_p}")
        except (TypeError, ValueError):
            bad.append(f"{ticker} non-numeric probability (AFG={afg_p}, Kalshi={kal_p})")
    check(
        "All probabilities in valid range",
        len(bad) == 0,
        f"Out-of-range: {bad[:5]}" if bad else f"{len(rows)} probability pairs verified"
    )
except Exception as e:
    check("All probabilities in valid range", False, str(e))


# ── CHECK 5: NO OPEN TICKERS WITH FUTURE SETTLEMENT DATES MARKED RESOLVED ────
print("\nCHECK 5: No premature resolutions (future settlement date)")
try:
    cur.execute("""
        SELECT ticker, close_date, resolution_date, outcome
        FROM predictions
        WHERE (outcome IS NOT NULL AND outcome != '')
        AND status NOT IN ('Void', 'Superseded')
    """)
    rows      = cur.fetchall()
    premature = []
    for ticker, close_date_raw, resolution_date_raw, outcome in rows:
        d = _parse_date(close_date_raw)
        if d and d > TODAY:
            # Allow early resolution if resolution_date is set and in the past
            # (contract settled early — e.g. official departed before contract close date)
            r = _parse_date(resolution_date_raw)
            if r is None or r > TODAY:
                premature.append(f"{ticker} (settles {d})")
    check(
        "No premature resolutions",
        len(premature) == 0,
        f"Future-dated resolutions: {premature}" if premature else f"{len(rows)} resolved contracts validated"
    )
except Exception as e:
    check("No premature resolutions", False, str(e))


# ── CHECK 6: OPEN TICKERS NOT DUPLICATED ACROSS ACTIVE BUY CALLS ─────────────
print("\nCHECK 6: No contradictory simultaneous BUY YES + BUY NO on same ticker")
try:
    cur.execute("""
        SELECT ticker, published_date, recommendation
        FROM predictions
        WHERE (outcome IS NULL OR outcome = '')
        AND recommendation IN ('BUY YES', 'BUY NO')
        AND status NOT IN ('Void', 'Superseded')
        ORDER BY ticker, published_date
    """)
    rows = cur.fetchall()
    # Group by ticker, check if the LATEST call per ticker is consistent
    # (Multiple calls = Bayesian updating = fine. Only flag if same date has conflicting calls.)
    from collections import defaultdict
    by_ticker_date = defaultdict(list)
    for ticker, pub_date, rec in rows:
        by_ticker_date[(ticker, pub_date)].append(rec)
    conflicts = []
    for (ticker, pub_date), recs in by_ticker_date.items():
        unique_recs = set(recs)
        if "BUY YES" in unique_recs and "BUY NO" in unique_recs:
            conflicts.append(f"{ticker} on {pub_date}: both BUY YES and BUY NO published same day")
    check(
        "No same-date BUY YES + BUY NO conflicts per ticker",
        len(conflicts) == 0,
        f"Conflicts: {conflicts}" if conflicts else "No contradictory same-day calls found"
    )
except Exception as e:
    check("No same-date BUY YES + BUY NO conflicts per ticker", False, str(e))


# ── CHECK 7: FINAL-CALL SCORING COMPLIANCE (replaces first-call dedup) ───────
print("\nCHECK 7: Final-call scoring compliance")
# Verify that for each resolved ticker, there is at least one published
# BUY YES or BUY NO call at or before the settlement date.
# Bayesian updating (multiple calls per ticker) is EXPECTED and correct.
try:
    cur.execute("""
        SELECT DISTINCT ticker, close_date
        FROM predictions
        WHERE (outcome IS NOT NULL AND outcome != '')
        AND status NOT IN ('Void', 'Superseded')
    """)
    resolved = cur.fetchall()
    unscorable = []
    for ticker, close_date_raw in resolved:
        settle = _parse_date(close_date_raw)
        cur.execute("""
            SELECT COUNT(*) FROM predictions
            WHERE ticker = ?
            AND recommendation IN ('BUY YES', 'BUY NO')
            AND status NOT IN ('Void', 'Superseded')
        """, (ticker,))
        total_calls = cur.fetchone()[0]
        # Find at least one call at or before settlement
        cur.execute("""
            SELECT recommendation, published_date
            FROM predictions
            WHERE ticker = ?
            AND recommendation IN ('BUY YES', 'BUY NO', 'NO TRADE')
            AND status NOT IN ('Void', 'Superseded')
            ORDER BY published_date ASC
        """, (ticker,))
        all_calls = cur.fetchall()
        has_scorable_call = False
        for rec, pub_raw in all_calls:
            pub = _parse_date(pub_raw)
            if settle is None or (pub is not None and pub <= settle):
                has_scorable_call = True
                break
        if not has_scorable_call:
            unscorable.append(ticker)

    total_resolved = len(resolved)
    # Note: multiple calls per ticker is expected Bayesian behavior
    cur.execute("""
        SELECT ticker, COUNT(*) as n
        FROM predictions
        WHERE (outcome IS NOT NULL AND outcome != '')
        AND recommendation IN ('BUY YES', 'BUY NO')
        AND status NOT IN ('Void', 'Superseded')
        GROUP BY ticker HAVING n > 1
    """)
    multi_call_tickers = cur.fetchall()

    detail = f"{total_resolved} resolved contracts, {len(multi_call_tickers)} with Bayesian updates (expected)"
    if unscorable:
        detail += f" | {len(unscorable)} unscorable (no call before settlement): {unscorable}"
    check(
        "All resolved contracts have a final scorable call",
        len(unscorable) == 0,
        detail
    )
    if multi_call_tickers:
        warn(
            "Bayesian updates noted (not a problem)",
            f"{len(multi_call_tickers)} tickers updated mid-cycle: "
            + ", ".join(t[0] for t in multi_call_tickers[:8])
            + (" ..." if len(multi_call_tickers) > 8 else "")
        )
except Exception as e:
    check("All resolved contracts have a final scorable call", False, str(e))


# ── CHECK 8: PUBLICATION DATE SEQUENCE VALID ──────────────────────────────────
print("\nCHECK 8: Publication dates not in future")
try:
    cur.execute("""
        SELECT ticker, published_date FROM predictions
        WHERE status NOT IN ('Void', 'Superseded')
        AND recommendation IN ('BUY YES', 'BUY NO', 'NO TRADE')
    """)
    rows        = cur.fetchall()
    future_pubs = []
    for ticker, pub_raw in rows:
        d = _parse_date(pub_raw)
        if d and d > TODAY:
            future_pubs.append(f"{ticker} ({pub_raw})")
    check(
        "No future-dated published calls",
        len(future_pubs) == 0,
        f"Future-dated publications: {future_pubs[:5]}" if future_pubs else f"{len(rows)} publication dates validated"
    )
except Exception as e:
    check("No future-dated published calls", False, str(e))


# ── CHECK 9: BRIER SCORE SANITY (AFG probability ≠ 0 or 100 on scored calls) ─
print("\nCHECK 9: AFG probability not at hard extremes (0% or 100%) on live calls")
try:
    cur.execute("""
        SELECT ticker, afg_probability, published_date
        FROM predictions
        WHERE (outcome IS NULL OR outcome = '')
        AND recommendation IN ('BUY YES', 'BUY NO')
        AND status NOT IN ('Void', 'Superseded')
    """)
    rows    = cur.fetchall()
    extreme = []
    for ticker, p_raw, pub in rows:
        try:
            p = float(p_raw)
            p_norm = p if p <= 1.0 else p / 100.0
            if p_norm == 0.0 or p_norm == 1.0:
                extreme.append(f"{ticker} ({p_raw})")
        except (TypeError, ValueError):
            pass
    if extreme:
        warn(
            "Open calls with 0% or 100% AFG probability (review recommended)",
            f"Extreme probabilities: {extreme[:5]}"
        )
    else:
        check(
            "No open calls at hard 0% or 100% AFG probability",
            True,
            f"{len(rows)} open call probabilities checked"
        )
except Exception as e:
    check("No open calls at hard 0% or 100% AFG probability", False, str(e))


# ── CHECK 10: OUTCOME FORMAT (must be 0/1 integer, not YES/NO string) ────────
print("\nCHECK 10: Resolved outcomes stored as 0/1 (not YES/NO strings)")
try:
    cur.execute("""
        SELECT ticker, outcome
        FROM predictions
        WHERE outcome IS NOT NULL AND outcome != ''
        AND status NOT IN ('Void', 'Superseded')
    """)
    rows = cur.fetchall()
    bad_format = []
    for ticker, outcome in rows:
        s = str(outcome).strip().upper()
        if s not in ("0", "1"):
            bad_format.append(f"{ticker} (outcome={outcome!r})")
    check(
        "All resolved outcomes stored as 0 or 1",
        len(bad_format) == 0,
        f"Non-integer outcomes found: {bad_format[:10]}" if bad_format
        else f"{len(rows)} resolved outcomes validated as 0/1"
    )
except Exception as e:
    check("All resolved outcomes stored as 0 or 1", False, str(e))


# ── CHECK 11: NO DUPLICATE ACTIVE RESOLVED ROWS PER TICKER ───────────────────
print("\nCHECK 11: No duplicate active resolved rows per ticker")
try:
    cur.execute("""
        SELECT ticker, COUNT(*) as n
        FROM predictions
        WHERE outcome IS NOT NULL AND outcome != ''
        AND status NOT IN ('Void', 'Superseded')
        AND recommendation IN ('BUY YES', 'BUY NO')
        GROUP BY ticker
        HAVING n > 1
    """)
    dups = cur.fetchall()
    # Allow Bayesian updates (BUY NO → BUY YES on same ticker) only when
    # the calls have DIFFERENT published_dates. Flag same-date duplicates.
    real_dups = []
    for ticker, n in dups:
        cur.execute("""
            SELECT id, recommendation, afg_probability, published_date, outcome
            FROM predictions
            WHERE ticker = ?
            AND outcome IS NOT NULL AND outcome != ''
            AND status NOT IN ('Void', 'Superseded')
            AND recommendation IN ('BUY YES', 'BUY NO')
            ORDER BY id
        """, (ticker,))
        sub = cur.fetchall()
        # Check for identical recommendation+date combos (true duplicates)
        seen = {}
        for row_id, rec, afg_p, pub_date, outcome in sub:
            key = (rec, pub_date)
            if key in seen:
                real_dups.append(
                    f"{ticker}: id={seen[key]} and id={row_id} both have "
                    f"{rec} on {pub_date}"
                )
            else:
                seen[key] = row_id
    if real_dups:
        check(
            "No true duplicate resolved rows per ticker",
            False,
            f"Duplicates found: {real_dups[:5]}"
        )
    else:
        multi_note = (
            f"{len(dups)} tickers with Bayesian updates (legitimate) — "
            "no same-rec/same-date duplicates found"
        ) if dups else f"No duplicate resolved rows found"
        check("No true duplicate resolved rows per ticker", True, multi_note)
except Exception as e:
    check("No true duplicate resolved rows per ticker", False, str(e))


# ── CHECK 12: SCORECARD SPOT-CHECK (independent scoring vs build script) ─────
print("\nCHECK 12: Independent scoring spot-check")
try:
    cur.execute("""
        SELECT DISTINCT ticker
        FROM predictions
        WHERE outcome IS NOT NULL AND outcome != ''
        AND status NOT IN ('Void', 'Superseded')
        AND recommendation IN ('BUY YES', 'BUY NO')
    """)
    tickers = [r[0] for r in cur.fetchall()]

    correct = 0
    incorrect = 0
    scoring_errors = []

    for ticker in tickers:
        # Final call = last BUY YES/BUY NO row by id
        cur.execute("""
            SELECT id, recommendation, afg_probability, outcome
            FROM predictions
            WHERE ticker = ?
            AND outcome IS NOT NULL AND outcome != ''
            AND status NOT IN ('Void', 'Superseded')
            AND recommendation IN ('BUY YES', 'BUY NO')
            ORDER BY id DESC LIMIT 1
        """, (ticker,))
        row = cur.fetchone()
        if not row:
            continue
        row_id, rec, afg_p, outcome_raw = row
        try:
            o = int(str(outcome_raw).strip())
            assert o in (0, 1)
        except (ValueError, AssertionError):
            scoring_errors.append(f"{ticker}: non-integer outcome={outcome_raw!r}")
            continue

        if (rec == "BUY YES" and o == 1) or (rec == "BUY NO" and o == 0):
            correct += 1
        else:
            incorrect += 1

    n = correct + incorrect
    acc = correct / n * 100 if n else 0

    detail = (
        f"{n} positions scored independently — "
        f"{correct} Correct / {incorrect} Incorrect / {acc:.1f}% accuracy"
    )
    if scoring_errors:
        detail += f" | ERRORS: {scoring_errors[:5]}"
    check(
        "Independent scoring completed without errors",
        len(scoring_errors) == 0,
        detail
    )
    # Always surface the accuracy number regardless of pass/fail
    print(f"         ► Verified accuracy: {correct}/{n} = {acc:.1f}%")
except Exception as e:
    check("Independent scoring completed without errors", False, str(e))


# ── SUMMARY ───────────────────────────────────────────────────────────────────
conn.close()

passed  = sum(1 for r in results if r[0] == PASS)
failed  = sum(1 for r in results if r[0] == FAIL)
warned  = sum(1 for r in results if r[0] == WARN)
total   = passed + failed

print(f"\n{'='*62}")
print(f"RESULTS: {passed}/{total} checks passed (12-check suite)", end="")
if warned:
    print(f"  |  {warned} warning(s)", end="")
print()
print(f"{'='*62}")

if exit_code == 0:
    print(f"\n✅ All checks passed. Safe to run the cycle.\n")
else:
    print(f"\n🚫 {failed} check(s) failed. Fix before publishing.\n")
    for status, name, detail in results:
        if status == FAIL:
            print(f"   FAILED: {name}")
            if detail:
                print(f"           {detail}")

# ── LOG ───────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
with open(LOG_PATH, "a", encoding="utf-8") as f:
    f.write(f"\n{TODAY_STR} — {passed}/{total} passed")
    if warned:
        f.write(f", {warned} warnings")
    if exit_code:
        f.write(" [FAILED]")
    f.write("\n")
    for status, name, detail in results:
        f.write(f"  {status}  {name}")
        if detail:
            f.write(f"\n         {detail}")
        f.write("\n")

sys.exit(exit_code)
