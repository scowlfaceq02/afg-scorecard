"""
check_blanche.py — shows every Blanche-related row in the database.
Run: python3 check_blanche.py
"""
from db import get_conn

with get_conn() as conn:
    rows = conn.execute(
        """SELECT id, market, kalshi_ticker, report_date,
                  kalshi_price, afg_probability, recommendation,
                  status, outcome, brier_score, contract_close_date
           FROM predictions
           WHERE market LIKE '%Attorney General%'
              OR market LIKE '%Blanche%'
              OR kalshi_ticker LIKE '%NEXTAG%'
           ORDER BY id"""
    ).fetchall()

if not rows:
    print("No Blanche rows found in database.")
else:
    print(f"Found {len(rows)} Blanche-related row(s):\n")
    for r in rows:
        outcome_txt = {1:"YES",0:"NO",None:"NULL"}.get(r[8],"?")
        if r[7] == "Resolved":
            rec = r[6]
            correct = (rec=="BUY YES" and r[8]==1) or (rec=="BUY NO" and r[8]==0)
            verdict = "CORRECT" if correct else "INCORRECT"
        else:
            verdict = r[7]
        print(f"  id={r[0]}")
        print(f"    Market     : {r[1]}")
        print(f"    Ticker     : {r[2]}")
        print(f"    Report date: {r[3]}")
        print(f"    Kalshi     : {r[4]:.0%}  AFG: {r[5]:.0%}")
        print(f"    AFG called : {r[6]}")
        print(f"    Status     : {r[7]}  Outcome: {outcome_txt}  -> {verdict}")
        print(f"    Brier      : {r[9]}  Close date: {r[10]}")
        print()
