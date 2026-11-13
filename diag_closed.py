"""
diag_closed.py  --  November 12th, 2026.  READ-ONLY: changes nothing.
================================================================================
Why is the Closed Positions table empty?  This shows how closures are recorded
in afg_scorecard.db for every settled position, and for the five positions the
November 6th scorecard listed as closed (Fed rate hike, Alcaraz, Fed September,
Isaias, hottest July).

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 diag_closed.py
"""
import sqlite3

DB = "afg_scorecard.db"
FIVE = ["FEDHIKE-26DEC31", "KXATP-26USO-ALC", "KXFEDDECISION-26SEP-H0",
        "KXFIRSTHURRICANE-26DEC01ATL-ISA", "KXHMONTH-26JUL"]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cols = {r[1] for r in conn.execute("PRAGMA table_info(predictions)")}
print("columns present:", ", ".join(c for c in ("afg_closed", "afg_closed_date", "afg_closed_reason",
                                                 "published_date", "report_date", "close_date",
                                                 "resolution_date") if c in cols) or "none of the closure columns")

n_nt = conn.execute("SELECT COUNT(*) FROM predictions WHERE recommendation='NO TRADE' "
                    "AND status NOT IN ('Void','Superseded')").fetchone()[0]
print(f"\n1. Rows whose recommendation is 'NO TRADE': {n_nt}   (the builder only looks for these)")

if "afg_closed" in cols:
    rows = conn.execute(
        "SELECT id, COALESCE(NULLIF(ticker,''), kalshi_ticker) AS t, report_date, recommendation, "
        "afg_closed_date, status, outcome, resolution_date FROM predictions "
        "WHERE afg_closed=1 AND status NOT IN ('Void','Superseded') ORDER BY t, id").fetchall()
    resolved = [r for r in rows if r["outcome"] not in (None, "")]
    print(f"\n2. Rows flagged afg_closed=1: {len(rows)}   of which settled (outcome set): {len(resolved)}")
    for r in resolved:
        print(f"   id={r['id']:<5} {r['t']:<38} {r['recommendation']:<8} called {r['report_date']} "
              f"closed {r['afg_closed_date']}  outcome={r['outcome']}  resolved {r['resolution_date']}")

print("\n3. The five positions the November 6th scorecard listed as closed (every row):")
sel = ["id", "report_date", "recommendation", "afg_probability", "kalshi_price", "status", "outcome", "resolution_date"]
sel += [c for c in ("afg_closed", "afg_closed_date") if c in cols]
for t in FIVE:
    print(f"\n   {t}")
    rs = conn.execute(f"SELECT {', '.join(sel)} FROM predictions WHERE COALESCE(NULLIF(ticker,''), kalshi_ticker)=? "
                      f"ORDER BY id", (t,)).fetchall()
    if not rs:
        print("     (no rows)")
    for r in rs:
        print("     " + "  ".join(f"{k}={r[k]}" for k in sel))
conn.close()
