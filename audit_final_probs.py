"""
audit_final_probs.py  --  November 11th, 2026
================================================================================
Compares the probability stored for every SCORED (resolved) position with the
last call AFG actually published for it, taken from data\\price_history.csv.

  python3 audit_final_probs.py            report only, changes nothing
  python3 audit_final_probs.py --apply    corrects the rows it can prove

What counts as proof: price_history.csv has a dated BUY call on the same ticker,
in the same direction as the stored row, on or before the settlement date, whose
AFG probability or Kalshi price differs from the stored row. --apply copies that
call's afg_probability and kalshi_price (and recomputes edge_score). It never
changes outcome, direction, report_date or resolution_date. A backup of the
database is written first.

Rows whose direction differs from the last published call are listed for manual
review and are never changed. price_history.csv starts 2026-10-30, so positions
repriced before that date cannot be checked here.
"""
import csv
import datetime as dt
import shutil
import sqlite3
import sys
from collections import defaultdict

DB, HIST = "afg_scorecard.db", "data/price_history.csv"
APPLY = "--apply" in sys.argv


def d(v):
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(str(v).strip(), f).date()
        except ValueError:
            pass
    return None


def direction(rec):
    r = str(rec or "").upper()
    return "BUY YES" if "BUY YES" in r else "BUY NO" if "BUY NO" in r else "NO TRADE"


hist = defaultdict(list)
with open(HIST, newline="", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        day = d(r["log_date"])
        if day:
            hist[r["kalshi_ticker"].strip()].append(
                (day, float(r["kalshi_price"]), float(r["afg_probability"]),
                 direction(r["recommendation"])))

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, ticker, kalshi_ticker, recommendation, afg_probability, kalshi_price, "
    "resolution_date, outcome FROM predictions "
    "WHERE outcome IN (0,1,'0','1') AND status NOT IN ('Void','Superseded') "
    "ORDER BY id").fetchall()

# the scored row per ticker is the latest active row
scored = {}
for r in rows:
    scored[r["ticker"] or r["kalshi_ticker"]] = r

fixes, review, ok, unchecked = [], [], 0, 0
for t, r in sorted(scored.items()):
    res = d(r["resolution_date"]) or dt.date.max
    calls = sorted(c for c in hist.get(t, []) if c[0] <= res)
    if not calls:
        unchecked += 1
        continue
    last_buy = next((c for c in reversed(calls) if c[3] != "NO TRADE"), None)
    if last_buy is None:
        review.append((t, "history shows only NO TRADE before settlement"))
        continue
    if last_buy[3] != direction(r["recommendation"]):
        review.append((t, f"stored {direction(r['recommendation'])} but last published "
                          f"call on {last_buy[0]} was {last_buy[3]}"))
        continue
    if (abs(last_buy[2] - float(r["afg_probability"])) > 0.0051
            or abs(last_buy[1] - float(r["kalshi_price"])) > 0.0051):
        fixes.append((r, last_buy))
    else:
        ok += 1

print(f"{len(scored)} scored positions | {ok} match their last published call | "
      f"{unchecked} not in price_history.csv (repriced before 2026-10-30 cannot be checked)")
print()
if fixes:
    print("STORED PROBABILITY DIFFERS FROM THE LAST PUBLISHED CALL:")
    for r, c in fixes:
        t = r["ticker"] or r["kalshi_ticker"]
        so = float(r["afg_probability"]); sm = float(r["kalshi_price"])
        b_old = (so - int(r["outcome"])) ** 2
        b_new = (c[2] - int(r["outcome"])) ** 2
        print(f"  {t}  {direction(r['recommendation'])}  stored {so:.0%}/{sm:.0%} -> "
              f"published {c[2]:.0%}/{c[1]:.0%} on {c[0]}   Brier {b_old:.3f} -> {b_new:.3f}")
else:
    print("No scored position differs from its last published call.")
if review:
    print("\nNEEDS MANUAL REVIEW (nothing will be changed):")
    for t, why in review:
        print(f"  {t}: {why}")

if APPLY and fixes:
    backup = DB + ".bak_audit_2026-11-11"
    shutil.copyfile(DB, backup)
    for r, c in fixes:
        conn.execute("UPDATE predictions SET afg_probability=?, kalshi_price=?, edge_score=? "
                     "WHERE id=?", (c[2], c[1], round(c[2] - c[1], 4), r["id"]))
    conn.commit()
    print(f"\nApplied {len(fixes)} correction(s). Backup: {backup}")
    print("Now run:  python3 verify_afg.py   then   python3 06_build_scorecard.py")
elif fixes:
    print("\nReport only. To correct these, run:  python3 audit_final_probs.py --apply")
conn.close()
