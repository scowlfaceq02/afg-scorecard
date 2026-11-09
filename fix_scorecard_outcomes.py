"""
fix_scorecard_outcomes.py  —  AFG Full Scorecard Outcome Correction
====================================================================
Corrects ALL outcome errors identified during the November 2026
full-verification audit of the 26 resolved scorecard positions.

VERIFIED FACTS (sources confirmed by web research):
  #2  Fed July — maintained rates Jul 2026              → outcome should be 1
  #3  Oregon drought — 90% of OR in D3/D4 drought       → outcome should be 1
  #5  FedEx St. Jude — Scheffler WON Jun 2026           → outcome should be 1
  #7  TOUR Championship — Scheffler WON Aug 2026        → outcome should be 1
  #8  Earthquake M7.8+ before Sep 1 — M7.8 Mindanao    → outcome should be 1
       hit Jun 7 2026 (before Sep 1)
  #9  US Open — Alcaraz WON 2026 US Open                → outcome should be 1
  #10 July 2026 hottest July on record                  → outcome should be 1
  #12 Fed rate hike before 2027 — Fed hiked Sep 2026    → outcome should be 1
  #16 Big Brother Rick Devens WON                       → outcome should be 1
  #19 Blanche AG committee advanced Aug 4 (before Oct1) → outcome should be 1
  #24 Major hurricanes (Cat3+) > 0 in 2026 season       → outcome should be 1
  #25 Dodgers won 2026 World Series                     → outcome should be 1
  #26 F1 — Antonelli WON                                → outcome should be 1

CONFIRMED CORRECT (no change needed):
  #1  3M Open — Scheffler: Koivun won, Scheffler was 2nd → outcome=0  ✓ OK
  #4  Spider-Man RT >91 — RT=88%, below 91              → outcome=0  ✓ OK
  #6  BMW Championship — Clark won, Scheffler tied 12th → outcome=0  ✓ OK
  #11 Fed Sep — hiked 25bps Sep 16 (did not maintain)   → outcome=0  ✓ OK
  #13 Big Brother Dee — Devens won, not Dee             → outcome=0  ✓ OK
  #14 LeBron — Cleveland — LeBron signed with 76ers     → outcome=0  ✓ OK
  #15 LeBron — Miami — LeBron signed with 76ers         → outcome=0  ✓ OK
  #17 Big Brother Drew Campbell — Devens won, not Drew  → outcome=0  ✓ OK
  #18 Big Brother Yash — Devens won, not Yash           → outcome=0  ✓ OK
  #20-23 Hurricane name firsts (Fay/Gonzalo/Hanna/Isaias)
         Fay formed Sep 20, Gonzalo Sep 24. Season had
         no storms before Fay. Markets priced on 1st named
         storm of given name — stored outcome=0 for each
         (storms did not form by deadline) ✓ OK per Kalshi
         settlement logic (requires confirmation of contract wording)

SCORING IMPACT:
  Before fix: DB shows 15 Correct, 11 Incorrect (57.7% accuracy)
  After fix:  Correct scoring reflects actual call outcomes

Run from C:\\Users\\qwhit\\AFG\\:
    python3 fix_scorecard_outcomes.py
"""

import sqlite3

DB_PATH = "afg_scorecard.db"

# ── CORRECTIONS: (ticker_fragment, market_fragment, correct_outcome, note) ──
CORRECTIONS = [
    # (2) Fed July — Fed maintained (did not cut/hike) → YES resolved
    {
        "ticker":  "KXFEDRATE",
        "market":  "July",
        "outcome": 1,
        "note":    "Fed maintained rates at July 2026 meeting — outcome should be 1 (YES)"
    },
    # (3) Oregon drought — >90% of OR in D3/D4 by summer 2026
    {
        "ticker":  None,  # match by market text
        "market":  "Oregon",
        "outcome": 1,
        "note":    "Oregon drought exceeded D3/D4 threshold — outcome should be 1 (YES)"
    },
    # (5) FedEx St. Jude — Scheffler WON
    {
        "ticker":  None,
        "market":  "FedEx",
        "outcome": 1,
        "note":    "Scheffler won FedEx St. Jude 2026 — BUY NO was incorrect"
    },
    # (7) TOUR Championship — Scheffler WON
    {
        "ticker":  None,
        "market":  "TOUR Championship",
        "outcome": 1,
        "note":    "Scheffler won TOUR Championship 2026 — BUY NO was incorrect"
    },
    # (8) Earthquake M7.8+ before Sep 1 — DID happen (Mindanao Jun 7)
    {
        "ticker":  None,
        "market":  "earthquake",
        "outcome": 1,
        "note":    "M7.8 Mindanao earthquake Jun 7 2026 — event occurred before Sep 1"
    },
    # (9) US Open — Alcaraz WON
    {
        "ticker":  None,
        "market":  "Alcaraz",
        "outcome": 1,
        "note":    "Alcaraz won 2026 US Open — BUY YES call was correct"
    },
    # (10) July 2026 hottest July on record
    {
        "ticker":  None,
        "market":  "hottest",
        "outcome": 1,
        "note":    "July 2026 was hottest US July on record — BUY YES call was correct"
    },
    # (12) Fed rate hike before 2027 — DID happen (Sep 2026)
    {
        "ticker":  None,
        "market":  "hike",
        "outcome": 1,
        "note":    "Fed hiked 25bps Sep 2026 — event occurred before 2027"
    },
    # (16) Big Brother Rick Devens WON
    {
        "ticker":  None,
        "market":  "Devens",
        "outcome": 1,
        "note":    "Rick Devens won Big Brother — BUY NO was incorrect"
    },
    # (19) Blanche AG committee advanced Aug 4 (before Oct 1)
    {
        "ticker":  None,
        "market":  "Blanche",
        "outcome": 1,
        "note":    "Blanche AG committee advanced Aug 4 2026, before Oct 1 — BUY NO was incorrect"
    },
    # (24) Major hurricanes (Cat 3+) — season DID produce major hurricanes
    {
        "ticker":  None,
        "market":  "major hurricane",
        "outcome": 1,
        "note":    "2026 season produced Cat 3+ hurricanes — BUY NO was incorrect"
    },
    # (25) Dodgers WON 2026 World Series
    {
        "ticker":  None,
        "market":  "Dodgers",
        "outcome": 1,
        "note":    "Dodgers won 2026 World Series — BUY NO was incorrect"
    },
    # (26) F1 Antonelli WON
    {
        "ticker":  None,
        "market":  "Antonelli",
        "outcome": 1,
        "note":    "Antonelli won F1 race — BUY NO was incorrect"
    },
]

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

print("=" * 68)
print("AFG SCORECARD OUTCOME CORRECTION — November 2026 Audit")
print("=" * 68)
print(f"\nApplying {len(CORRECTIONS)} corrections...\n")

total_updated = 0

for fix in CORRECTIONS:
    ticker  = fix.get("ticker")
    market  = fix.get("market")
    outcome = fix["outcome"]
    note    = fix["note"]

    # Find matching resolved rows with wrong outcome
    if ticker:
        cur.execute("""
            SELECT id, ticker, market, recommendation, afg_probability,
                   outcome, status
            FROM predictions
            WHERE (ticker LIKE ? OR kalshi_ticker LIKE ?)
              AND outcome IS NOT NULL AND outcome != ''
              AND status NOT IN ('Void','Superseded')
        """, (f"%{ticker}%", f"%{ticker}%"))
    else:
        cur.execute("""
            SELECT id, ticker, market, recommendation, afg_probability,
                   outcome, status
            FROM predictions
            WHERE market LIKE ?
              AND outcome IS NOT NULL AND outcome != ''
              AND status NOT IN ('Void','Superseded')
        """, (f"%{market}%",))

    rows = cur.fetchall()

    if not rows:
        print(f"  ⚠  NO MATCH for: {note}")
        print(f"     Search: ticker={ticker}, market={market}")
        print()
        continue

    for row in rows:
        row_id, row_ticker, row_market, rec, afg_pct, cur_outcome, status = row
        if str(cur_outcome) == str(outcome):
            print(f"  ── id={row_id} already outcome={outcome}, no change needed")
            print(f"     {row_market[:70] if row_market else row_ticker}")
            print()
            continue

        cur.execute("""
            UPDATE predictions
            SET outcome = ?
            WHERE id = ?
        """, (outcome, row_id))

        brier = (float(afg_pct) / 100.0 - outcome) ** 2 if afg_pct else None
        brier_str = f"{brier:.4f}" if brier is not None else "N/A"

        # Scoring verdict
        if rec == "BUY YES" and outcome == 1:
            verdict = "✓ Correct"
        elif rec == "BUY YES" and outcome == 0:
            verdict = "✗ Incorrect"
        elif rec == "BUY NO" and outcome == 0:
            verdict = "✓ Correct"
        elif rec == "BUY NO" and outcome == 1:
            verdict = "✗ Incorrect"
        else:
            verdict = "?"

        print(f"  FIXED  id={row_id} | {rec} | AFG={afg_pct}%")
        print(f"         outcome: {cur_outcome} → {outcome} | {verdict} | Brier={brier_str}")
        print(f"         {row_market[:70] if row_market else row_ticker}")
        print(f"         Note: {note}")
        print()
        total_updated += 1

conn.commit()

# ── FINAL SCORECARD SUMMARY ──────────────────────────────────────────────────
print("=" * 68)
print("POST-CORRECTION SCORECARD SUMMARY")
print("=" * 68)

cur.execute("""
    SELECT recommendation, afg_probability, outcome
    FROM predictions
    WHERE outcome IS NOT NULL AND outcome != ''
      AND status NOT IN ('Void','Superseded')
      AND recommendation IN ('BUY YES','BUY NO')
""")
scored_rows = cur.fetchall()

correct = 0
incorrect = 0
total_brier = 0.0

for rec, afg_pct, outcome in scored_rows:
    try:
        p = float(afg_pct) / 100.0
        o = int(outcome)
    except (TypeError, ValueError):
        continue

    brier = (p - o) ** 2
    total_brier += brier

    if (rec == "BUY YES" and o == 1) or (rec == "BUY NO" and o == 0):
        correct += 1
    else:
        incorrect += 1

n = correct + incorrect
accuracy = correct / n * 100 if n else 0
avg_brier = total_brier / n if n else 0

print(f"\n  Total scored positions : {n}")
print(f"  Correct                : {correct}")
print(f"  Incorrect              : {incorrect}")
print(f"  Accuracy               : {accuracy:.1f}%")
print(f"  Mean Brier Score       : {avg_brier:.4f}")
print(f"\n  Total outcome updates  : {total_updated}")
print()

conn.close()
print("Done. Run 06_build_scorecard.py to regenerate the scorecard.")
