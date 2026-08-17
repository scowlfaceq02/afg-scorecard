"""
check_allowlist.py — diagnoses why a ticker isn't matching the allowlist.
Run: python3 check_allowlist.py
"""
import os
from db import get_conn

PATH = "verified_early_resolutions.txt"

print("=" * 62)
print("  ALLOWLIST DIAGNOSTIC")
print("=" * 62)

# 1. Does the file exist and where?
print(f"\n1. FILE CHECK")
if os.path.exists(PATH):
    size = os.path.getsize(PATH)
    print(f"   FOUND: {PATH} ({size} bytes)")
else:
    print(f"   *** MISSING: {PATH} not in {os.getcwd()}")
    # look for near-miss filenames
    for f in os.listdir("."):
        if "verified" in f.lower() or "early" in f.lower():
            print(f"   Possible match found: '{f}'")
    raise SystemExit

# 2. Raw contents
print(f"\n2. RAW FILE CONTENTS (non-comment lines)")
raw_lines = []
for i, line in enumerate(open(PATH, encoding="utf-8"), 1):
    s = line.strip()
    if s and not s.startswith("#"):
        raw_lines.append((i, line.rstrip("\n")))
        print(f"   line {i}: {repr(line.rstrip(chr(10)))}")
if not raw_lines:
    print("   *** NO DATA LINES FOUND — file is all comments or empty")

# 3. Parsed tickers
print(f"\n3. PARSED TICKERS")
allowlist = set()
for _, line in raw_lines:
    t = line.split("|")[0].strip()
    if t:
        allowlist.add(t)
        print(f"   {repr(t)}")

# 4. Resolved tickers in the database
print(f"\n4. RESOLVED TICKERS IN DATABASE")
with get_conn() as conn:
    rows = conn.execute(
        "SELECT DISTINCT kalshi_ticker, market FROM predictions WHERE status='Resolved'"
    ).fetchall()
for tkr, mkt in rows:
    match = "MATCH" if tkr in allowlist else "not in allowlist"
    print(f"   {repr(tkr)}  ->  {match}")
    print(f"        ({mkt})")

# 5. Verdict
print(f"\n5. VERDICT")
db_tickers = {r[0] for r in rows}
missing = [t for t in db_tickers if t not in allowlist]
if not missing:
    print("   All resolved tickers are in the allowlist.")
else:
    print("   These resolved tickers are NOT matching the allowlist:")
    for t in missing:
        print(f"     {repr(t)}")
        for a in allowlist:
            if a.replace(" ", "") == str(t).replace(" ", ""):
                print(f"       -> near match in file: {repr(a)} (whitespace differs)")
            elif a.upper() == str(t).upper():
                print(f"       -> near match in file: {repr(a)} (case differs)")
print("=" * 62)
