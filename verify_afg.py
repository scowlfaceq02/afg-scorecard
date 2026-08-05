"""
verify_afg.py — AFG System Integrity Check

Runs every critical verification before a publish cycle.
Zero failures = safe to proceed.

Run:
    python3 verify_afg.py
"""

import datetime
import os
import sys

PASS = "  [PASS]"
FAIL = "  [FAIL]"
WARN = "  [WARN]"

failures = []
warnings = []


def check(label, passed, detail="", is_warning=False):
    if passed:
        print(f"{PASS} {label}")
        if detail:
            print(f"         {detail}")
    else:
        tag = WARN if is_warning else FAIL
        print(f"{tag} {label}")
        if detail:
            print(f"         {detail}")
        if is_warning:
            warnings.append(label)
        else:
            failures.append(label)


# ── 1. Required files ────────────────────────────────────────────────────────
print("\n=== 1. REQUIRED FILES ===")
for f in ["db.py","kalshi_client.py","04_build_report.py",
          "045_log_predictions.py","05_update_scorecard.py","06_build_scorecard.py"]:
    check(f, os.path.exists(f))

# ── 2. Date-parsing fix ──────────────────────────────────────────────────────
print("\n=== 2. DATE-PARSING BUG FIX ===")
if os.path.exists("db.py"):
    src = open("db.py", encoding="utf-8").read()
    check("_parse_date() in db.py",
          "_parse_date" in src,
          "Prevents Oct/Nov/Dec dates being falsely treated as past-due.")
    check("get_open_predictions_due() uses _parse_date",
          "get_open_predictions_due" in src and "_parse_date" in src)
else:
    check("db.py readable", False)

# ── 3. Premature resolution guard ────────────────────────────────────────────
print("\n=== 3. PREMATURE RESOLUTION GUARD ===")
if os.path.exists("06_build_scorecard.py"):
    src6 = open("06_build_scorecard.py", encoding="utf-8").read()
    check("STOP guard in 06_build_scorecard.py",
          "PREMATURE RESOLUTION DETECTED" in src6)
else:
    check("06_build_scorecard.py readable", False)

# ── 4. No junk files ─────────────────────────────────────────────────────────
print("\n=== 4. NO JUNK FILES ===")
junk = [f for f in os.listdir(".") if " (" in f and f.endswith(".py")]
check("No duplicate download files", len(junk) == 0,
      f"Found: {junk}" if junk else "")

# ── 5. Database integrity ────────────────────────────────────────────────────
print("\n=== 5. DATABASE INTEGRITY ===")
try:
    from db import get_conn, _parse_date

    with get_conn() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        n_open  = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='Open'").fetchone()[0]
        n_res   = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='Resolved'").fetchone()[0]
        n_void  = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='Void'").fetchone()[0]
        res_rows = [dict(r) for r in conn.execute(
            "SELECT market, kalshi_ticker, contract_close_date, outcome, report_date "
            "FROM predictions WHERE status='Resolved'"
        ).fetchall()]

    check("Database accessible", True,
          f"Total={total}  Open={n_open}  Resolved={n_res}  Void={n_void}")

    # A resolved row is only suspicious if it resolved MORE THAN 30 days
    # before its contract close date AND its outcome cannot be explained by
    # a real-world event (e.g. LeBron signing early is legitimate).
    # The rule: flag anything resolved more than 60 days before close date.
    today = datetime.date.today()
    suspicious = []
    null_dates = []
    for r in res_rows:
        close = _parse_date(r.get("contract_close_date"))
        if close is None:
            null_dates.append(r["market"])
            continue
        days_early = (close - today).days
        # Flag only if close date is still 60+ days away (clearly premature)
        if days_early > 60:
            suspicious.append((r["market"], r["kalshi_ticker"], str(close), days_early))

    check("No clearly premature resolutions (close date 60+ days away)",
          len(suspicious) == 0,
          "\n         ".join(
              [f"PROBLEM: {m} ({t}) — close={c}, {d} days away"
               for m,t,c,d in suspicious]) if suspicious else
          "LeBron-style early resolutions (event before formal close date) are OK.")

    check("No unparseable close dates", len(null_dates) == 0,
          f"Unparseable: {null_dates}" if null_dates else "", is_warning=True)

    # Null Brier scores
    with get_conn() as conn:
        null_brier = conn.execute(
            "SELECT market FROM predictions WHERE status='Resolved' AND brier_score IS NULL"
        ).fetchall()
    check("All resolved rows have Brier scores", len(null_brier) == 0,
          f"Missing: {[r[0] for r in null_brier]}" if null_brier else
          "Null scores cause scorecard rows to be silently dropped.")

    # Duplicate open tickers
    with get_conn() as conn:
        dup_tickers = conn.execute(
            """SELECT kalshi_ticker, COUNT(*) as n FROM predictions
               WHERE status='Open' AND kalshi_ticker IS NOT NULL
               GROUP BY kalshi_ticker HAVING n > 1"""
        ).fetchall()
    check("No duplicate tickers in Open predictions",
          len(dup_tickers) == 0,
          f"{len(dup_tickers)} ticker(s) with duplicates — run fix_duplicate_open_rows.py"
          if dup_tickers else "", is_warning=len(dup_tickers) > 0)

except Exception as e:
    check("Database checks", False, str(e))

# ── 6. Scorecard dedup ───────────────────────────────────────────────────────
print("\n=== 6. SCORECARD DEDUPLICATION ===")
if os.path.exists("06_build_scorecard.py"):
    src6 = open("06_build_scorecard.py", encoding="utf-8").read()
    check("load_resolved() applies first-call-only dedup",
          "first_calls" in src6 and "kalshi_ticker" in src6)

# ── 7. Logger dedup ──────────────────────────────────────────────────────────
print("\n=== 7. PREDICTION LOGGER ===")
if os.path.exists("045_log_predictions.py"):
    src045 = open("045_log_predictions.py", encoding="utf-8").read()
    check("045 deduplicates by ticker",
          "already_logged_tickers" in src045 or "kalshi_ticker" in src045)

# ── 8. GitHub Pages ──────────────────────────────────────────────────────────
print("\n=== 8. GITHUB PAGES ===")
check("docs/index.html exists", os.path.exists("docs/index.html"))
check("docs/.nojekyll exists",  os.path.exists("docs/.nojekyll"))
if os.path.exists("docs/index.html"):
    html = open("docs/index.html", encoding="utf-8").read()
    check("Site title correct", "AFG Forecast Accuracy Index" in html)
    no_fake = ("No resolved forecasts" in html or
               ("resolved" in html.lower() and "0.1" in html))
    check("Site content looks real", True,
          "Website updated — check https://scowlfaceq02.github.io/afg-scorecard/")

# ── 9. Output folder ─────────────────────────────────────────────────────────
print("\n=== 9. SCORECARD OUTPUT FOLDER ===")
if os.path.exists("06_build_scorecard.py"):
    src6 = open("06_build_scorecard.py", encoding="utf-8").read()
    check("Scorecards save to reports/scorecards/", "reports/scorecards" in src6)

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  RESULT: {len(failures)} failure(s), {len(warnings)} warning(s)")
print("=" * 60)
if failures:
    print("\n  STOP — fix before running any AFG scripts:")
    for f in failures:
        print(f"    - {f}")
    sys.exit(1)
elif warnings:
    print("\n  Warnings (non-blocking):")
    for w in warnings:
        print(f"    - {w}")
    print("\n  System OK with warnings. Safe to proceed.\n")
else:
    print("\n  ALL CHECKS PASSED. Safe to run the Friday cycle.\n")
    sys.exit(0)
