"""
run_cycle.py  --  the whole AFG pipeline in one command (November 11th, 2026)
================================================================================
Run this after saving Claude's three files into data\\ :

    cd C:\\Users\\qwhit\\AFG
    python3 run_cycle.py

What it does, in order, stopping at the first problem:
  1. Pre-flight   the three input files exist, are today's, and the scripts
                  in this folder are the current versions
  2. verify_afg.py            integrity check BEFORE anything changes
  3. 04_build_report.py       report, workbook, Substack post, X post, Note
  4. 045_log_predictions.py   logs today's calls
  5. ticker backfill          fills `ticker` on newly logged rows
  6. 05_update_scorecard.py   records any settlements from Kalshi
  7. verify_afg.py            all 13 checks again, incl. Kalshi settlement check
  8. 06_build_scorecard.py    builds the Word scorecard and the website
  9. Accuracy match           06's accuracy must equal Check 12's
 10. Push                     asks you to type PUSH, then git add/commit/push

Everything it prints is also saved to logs\\run_cycle_<date>.log. If it stops,
send that file to Claude instead of copying from the window.
"""
import csv
import datetime as dt
import os
import re
import sqlite3
import subprocess
import sys

TODAY = dt.date.today()
STAMP = TODAY.isoformat()
os.makedirs("logs", exist_ok=True)
LOG_PATH = os.path.join("logs", f"run_cycle_{STAMP}.log")
_log = open(LOG_PATH, "a", encoding="utf-8")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def say(text=""):
    print(text, flush=True)
    _log.write(text + "\n")
    _log.flush()


def banner(n, title):
    say("")
    say("=" * 66)
    say(f"STEP {n}: {title}")
    say("=" * 66)


def stop(reason, fix):
    say("")
    say("!" * 66)
    say(f"STOPPED: {reason}")
    say(f"FIX:     {fix}")
    say("Nothing has been pushed or published.")
    say(f"Full log: {LOG_PATH}  (send this file to Claude if you need help)")
    say("!" * 66)
    _log.close()
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass
    sys.exit(1)


def run(cmd):
    """Run a command, show its output live, return (exit code, full output)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, encoding="utf-8", errors="replace")
    lines = []
    for line in proc.stdout:
        line = line.rstrip("\n")
        lines.append(line)
        say("  " + line)
    proc.wait()
    return proc.returncode, "\n".join(lines)


def py(script):
    return run([sys.executable, script])


# ── 1. PRE-FLIGHT ─────────────────────────────────────────────────────────────
banner(1, "Pre-flight checks")
say(f"Folder: {os.getcwd()}    Date: {TODAY:%A, %B} {TODAY.day}, {TODAY.year}")

required_scripts = ["verify_afg.py", "04_build_report.py", "045_log_predictions.py",
                    "05_update_scorecard.py", "06_build_scorecard.py", "check_settlements.py",
                    "afg_scorecard.db"]
missing = [f for f in required_scripts if not os.path.exists(f)]
if missing:
    stop(f"missing from this folder: {', '.join(missing)}",
         "run this from C:\\Users\\qwhit\\AFG (cd C:\\Users\\qwhit\\AFG)")

stray = [f for f in os.listdir(".") if re.search(r" \(\d+\)\.py$", f)]
if stray:
    stop(f"duplicate download(s) found: {', '.join(stray)}",
         "Windows saved a new file under a '(1)' name. Delete the old file, rename the new one "
         "to the plain name, then rerun.")

checks = {
    "check_settlements.py": "KALSHI_HISTORICAL_URL",
    "verify_afg.py": "CHECK 13",
    "06_build_scorecard.py": "check_settlements",
}
for f, marker in checks.items():
    if marker not in open(f, encoding="utf-8", errors="replace").read():
        stop(f"{f} is an old version", f"save the current {f} from Claude into this folder")

inputs = ["data/approved_predictions.csv", "data/approved_narrative.md", "data/raw_markets.xlsx"]
for f in inputs:
    if not os.path.exists(f):
        stop(f"{f} is missing", "save Claude's three files into C:\\Users\\qwhit\\AFG\\data\\")
    modified = dt.date.fromtimestamp(os.path.getmtime(f))
    if modified != TODAY:
        stop(f"{f} was last saved {modified}, not today",
             "the new download did not replace it. Save today's file from Claude into data\\ "
             "and replace the old one.")

with open("data/approved_predictions.csv", newline="", encoding="utf-8-sig") as fh:
    rows = list(csv.DictReader(fh))
dates = {r.get("report_date", "").strip() for r in rows}
if dates != {STAMP}:
    stop(f"approved_predictions.csv has report_date {sorted(dates)}, expected {STAMP}",
         "ask Claude to re-send today's approved_predictions.csv")
narr = open("data/approved_narrative.md", encoding="utf-8").read()
for section in ("## Executive Summary", "## Twitter Post", "## Substack Note"):
    if section not in narr:
        stop(f"approved_narrative.md has no '{section}' section",
             "ask Claude to re-send today's approved_narrative.md")
say(f"OK: scripts current; three input files saved today; {len(rows)} calls dated {STAMP}.")

# ── 2. VERIFY BEFORE ──────────────────────────────────────────────────────────
banner(2, "verify_afg.py (before any change)")
code, _ = py("verify_afg.py")
if code != 0:
    stop("verify_afg.py failed before the cycle started",
         "the database had a problem before today's run. Send the log to Claude.")

# ── 3. BUILD REPORT ───────────────────────────────────────────────────────────
banner(3, "04_build_report.py")
code, _ = py("04_build_report.py")
if code != 0:
    stop("04_build_report.py failed", "send the log to Claude")

# ── 4. LOG CALLS ──────────────────────────────────────────────────────────────
banner(4, "045_log_predictions.py")
code, _ = py("045_log_predictions.py")
if code != 0:
    stop("045_log_predictions.py failed", "send the log to Claude")

# ── 5. TICKER BACKFILL ────────────────────────────────────────────────────────
banner(5, "Fill ticker on newly logged rows")
conn = sqlite3.connect("afg_scorecard.db")
cur = conn.cursor()
cur.execute("""UPDATE predictions SET ticker = kalshi_ticker
               WHERE (ticker IS NULL OR ticker = '')
                 AND kalshi_ticker IS NOT NULL AND kalshi_ticker != ''""")
say(f"  ticker filled on {cur.rowcount} row(s)")
conn.commit()
conn.close()

# ── 6. SETTLEMENTS ────────────────────────────────────────────────────────────
banner(6, "05_update_scorecard.py")
code, _ = py("05_update_scorecard.py")
if code != 0:
    stop("05_update_scorecard.py failed", "send the log to Claude")

# ── 7. VERIFY AFTER ───────────────────────────────────────────────────────────
banner(7, "verify_afg.py (after today's changes)")
code, out = py("verify_afg.py")
if code != 0:
    stop("verify_afg.py failed after today's changes",
         "read the FAILED lines above. Send the log to Claude for a fix script.")
m = re.search(r"Verified accuracy:\s*(\d+)/(\d+)\s*=\s*([\d.]+)%", out)
if not m:
    stop("could not read the Check 12 accuracy line", "send the log to Claude")
check12 = float(m.group(3))
say(f"\n  Check 12 accuracy: {m.group(1)}/{m.group(2)} = {check12:.1f}%")

# ── 8. BUILD SCORECARD ────────────────────────────────────────────────────────
banner(8, "06_build_scorecard.py")
code, out = py("06_build_scorecard.py")
if code != 0:
    stop("06_build_scorecard.py stopped", "read the STOP lines above. Send the log to Claude.")
m6 = re.search(r"^\s*Accuracy\s*:\s*([\d.]+)%", out, re.MULTILINE)
if not m6:
    stop("could not read the accuracy line from 06_build_scorecard.py", "send the log to Claude")
acc06 = float(m6.group(1))

# ── 9. ACCURACY MATCH ─────────────────────────────────────────────────────────
banner(9, "Accuracy match")
say(f"  Check 12: {check12:.1f}%     06_build_scorecard.py: {acc06:.1f}%")
if abs(check12 - acc06) > 0.05:
    stop("the two accuracy figures differ", "do not publish. Send the log to Claude.")
say("  MATCH")

# ── 10. PUSH ──────────────────────────────────────────────────────────────────
banner(10, "Publish the scorecard")
say(f"  All checks passed. Verified accuracy {acc06:.1f}%.")
try:
    answer = input("  Type PUSH and press Enter to push the scorecard to the website "
                   "(anything else stops here): ").strip()
except EOFError:
    answer = ""
_log.write(f"  answer: {answer!r}\n")
if answer != "PUSH":
    say("  Not pushed. When ready, run:")
    say(f'    git add -A && git commit -m "cycle update {STAMP}" && git push')
else:
    run(["git", "add", "-A"])
    code, out = run(["git", "commit", "-m", f"cycle update {STAMP}"])
    if code != 0 and "nothing to commit" not in out:
        stop("git commit failed", "send the log to Claude")
    code, _ = run(["git", "push"])
    if code != 0:
        stop("git push failed",
             "check your internet connection or GitHub token, then run: git push")
    say("  Pushed. Open https://scowlfaceq02.github.io/afg-scorecard/ in a minute and confirm "
        f"it shows {acc06:.1f}%.")

# ── PUBLISH CHECKLIST ─────────────────────────────────────────────────────────
say("")
say("=" * 66)
say("NOW PUBLISH (in this order)")
say("=" * 66)
say(f"  1. Substack:      reports\\AFG_Substack_Post_{STAMP}.md")
say(f"  2. X:             reports\\AFG_Twitter_Post_{STAMP}.txt")
say(f"  3. Substack Note: reports\\AFG_Substack_Note_{STAMP}.txt  (add the link to today's post)")
res = f"reports\\scorecards\\AFG_Resolution_Post_{STAMP}.txt"
if os.path.exists(res.replace("\\", os.sep)):
    say(f"  4. Resolution post: {res}  (attach a scorecard screenshot)")
say(f"\nLog saved: {LOG_PATH}")
_log.close()
try:
    input("\nPress Enter to close...")
except EOFError:
    pass
