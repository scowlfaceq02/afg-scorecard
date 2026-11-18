"""
diag_accuracy_match.py  --  why do verify_afg.py check 12 and 06_build_scorecard.py disagree?
=============================================================================================
READ-ONLY. Changes nothing in afg_scorecard.db.

Check 12 picks each contract's final call as "the last BUY row by id that has an outcome".
06_build_scorecard.py picks "the last published call (BUY YES, BUY NO or NO TRADE) by
publication date, at or before settlement", and treats a final NO TRADE as a closed position.
When those two rules pick different rows, the accuracy figures differ.

This script scores every settled contract both ways, lists every contract where the two
disagree, and prints every row for those contracts so the cause is visible.

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 diag_accuracy_match.py
and send the whole output to Claude.
"""
import importlib.util
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("b", os.path.join(HERE, "06_build_scorecard.py"))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

conn = sqlite3.connect(os.path.join(HERE, "afg_scorecard.db"))
cur = conn.cursor()

# ---- method A: 06_build_scorecard.py ----
scored, closed = b.fetch_scored_positions(conn)
a_res = {r["ticker"]: ("closed" if r in closed else r["result"]) for r in scored + closed}
for r in closed:
    a_res[r["ticker"]] = "closed"
for r in scored:
    a_res[r["ticker"]] = r["result"]

# ---- method B: verify_afg.py check 12 ----
_p = b._parse_date
cur.execute("""SELECT DISTINCT ticker FROM predictions WHERE outcome IS NOT NULL AND outcome != ''
               AND status NOT IN ('Void','Superseded') AND recommendation IN ('BUY YES','BUY NO')""")
b_res = {}
for (t,) in cur.fetchall():
    cur.execute("""SELECT id, recommendation, outcome, COALESCE(afg_closed,0), afg_closed_date, resolution_date
                   FROM predictions WHERE ticker=? AND outcome IS NOT NULL AND outcome != ''
                   AND status NOT IN ('Void','Superseded') AND recommendation IN ('BUY YES','BUY NO')
                   ORDER BY id DESC LIMIT 1""", (t,))
    rid, rec, o, flag, cd, rd = cur.fetchone()
    c_, r_ = _p(cd), _p(rd)
    if flag and c_ is not None and (r_ is None or c_ <= r_):
        b_res[t] = "closed"
        continue
    o = int(str(o).strip()) if str(o).strip() in ("0", "1") else (1 if str(o).strip().upper() == "YES" else 0)
    b_res[t] = "Correct" if (rec == "BUY YES" and o == 1) or (rec == "BUY NO" and o == 0) else "Incorrect"

def summary(res):
    c = sum(v == "Correct" for v in res.values()); i = sum(v == "Incorrect" for v in res.values())
    return f"{c} correct / {i} incorrect / {sum(v == 'closed' for v in res.values())} closed = " \
           f"{(c / (c + i) * 100 if c + i else 0):.1f}%"

print("06_build_scorecard.py :", summary(a_res))
print("verify_afg.py check 12:", summary(b_res))

diff = sorted(t for t in set(a_res) | set(b_res) if a_res.get(t) != b_res.get(t))
print(f"\n{len(diff)} contract(s) scored differently:\n")
for t in diff:
    print(f"=== {t}:  06 says {a_res.get(t, 'not scored')}   |   check 12 says {b_res.get(t, 'not scored')}")
    cur.execute("""SELECT id, published_date, recommendation, afg_probability, kalshi_price, outcome, status,
                          close_date, resolution_date, COALESCE(afg_closed,0), afg_closed_date
                   FROM predictions WHERE ticker=? ORDER BY id""", (t,))
    print("   id    published    rec       afg   kal   outcome status      close       resolution  closed  closed_date")
    for r in cur.fetchall():
        print("   " + "  ".join(str(x) for x in r))
    print()
conn.close()
