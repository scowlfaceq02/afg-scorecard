"""
fix_scorecard_outcomes_v2.py  —  AFG Scorecard Correction (by row ID)
======================================================================
Fixes outcome errors AND voids duplicate rows identified in the
November 2026 full-verification audit.

DUPLICATE ANALYSIS
─────────────────
FEDHIKE-26DEC31 appears 4 times (ids 138, 163, 170, 176).
  → Keep the LAST published call (id=176, BUY YES 80%) as final-call.
  → Void ids 138, 163, 170 (earlier/superseded calls).

KXMLB-26-LAD (Dodgers) appears twice (ids 133, 179).
  → Keep id=179 (later row). Void id=133.

KXBIGBROTHER-26DEC31-DEE appears 3 times (ids 73, 209, 210).
  → Keep id=209 (most recent of the three). Void ids 73, 210.
  NOTE: id=73 has outcome=1 (wrong — Devens won, not Dee).
  Since we're voiding it, outcome on 73 doesn't matter.

KXBIGBROTHER-26DEC31-YAS appears twice (ids 128, 211).
  → Keep id=128 (has outcome recorded). Void id=211.

OUTCOME CORRECTIONS (all verified against real-world results)
──────────────────────────────────────────────────────────────
id=19   KXDROUGHTLEVEL-26JULLD4-OR  BUY NO  0.38  outcome 1→0
        Oregon D4 drought market: AFG called BUY NO.
        Oregon DID reach D4 → outcome=1 means YES (drought happened).
        BUY NO + outcome=1 = ✗ Incorrect. Currently correct (outcome=1).
        *** LEAVE AS IS — already correct ***

id=76   KXDROUGHTLEVEL-26JULLD4-OR  BUY YES 0.72  outcome 1
        BUY YES + outcome=1 = ✓ Correct. *** LEAVE AS IS ***

id=97   KXFEDDECISION-26SEP-H0  BUY YES 0.76  outcome=0
        Fed hiked in September — did NOT maintain.
        BUY YES (maintain) + outcome=0 (did not maintain) = ✗ Incorrect.
        *** LEAVE AS IS — this one is correctly scored Incorrect ***

id=117  KXBIGBROTHER-26DEC31-RIC  BUY NO  0.30  outcome=1
        Rick Devens WON → outcome=1 (YES he won).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

id=133  KXMLB-26-LAD  BUY NO  0.26  outcome=1  → VOID (duplicate; keep 179)

id=138  FEDHIKE-26DEC31  BUY NO  0.45  outcome=1  → VOID (superseded by 176)

id=151  KXF1-26-KA  BUY NO  0.70  outcome=1
        Antonelli WON → outcome=1 (YES). BUY NO + outcome=1 = ✗ Incorrect.
        *** CORRECT — leave as is ***

id=155  KXBLANCHEJUDICIARY  BUY NO  0.52  outcome=1
        Blanche advanced committee Aug 4 → outcome=1 (YES).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

id=159  KXHMONTH-26JUL  BUY YES  0.24  outcome=1
        July 2026 hottest on record → outcome=1 (YES).
        BUY YES + outcome=1 = ✓ Correct. *** CORRECT — leave as is ***

id=160  KXPGATOUR-FESJC26-SSCH  BUY NO  0.13  outcome=1
        Scheffler WON FedEx St. Jude → outcome=1 (YES).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

id=163  FEDHIKE-26DEC31  BUY NO  0.50  outcome=1  → VOID (superseded by 176)

id=169  KXEARTHQUAKEM-26AUG-78  BUY NO  0.05  outcome=1
        M7.8 Mindanao Jun 7 DID happen → outcome=1 (YES).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

id=170  FEDHIKE-26DEC31  BUY NO  0.48  outcome=1  → VOID (superseded by 176)

id=173  KXPGATOUR-TOC26-SSCH  BUY NO  0.18  outcome=1
        Scheffler WON TOUR Championship → outcome=1 (YES).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

id=175  KXATP-26USO-ALC  BUY YES  0.33  outcome=1
        Alcaraz WON US Open → outcome=1 (YES).
        BUY YES + outcome=1 = ✓ Correct. *** CORRECT — leave as is ***

id=176  FEDHIKE-26DEC31  BUY YES  0.80  outcome=1  ← KEEPER
        Fed DID hike before 2027 → outcome=1 (YES).
        BUY YES + outcome=1 = ✓ Correct. *** CORRECT — leave as is ***

id=179  KXMLB-26-LAD  BUY NO  0.25  outcome=1  ← KEEPER
        Dodgers WON WS → outcome=1 (YES).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

id=186  KXHURCTOTMAJ-26DEC01-T0  BUY NO  0.22  outcome=1
        Season had Cat 3+ hurricanes → outcome=1 (YES).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

id=189  KXFIRSTHURRICANE-26DEC01ATL-FAY  BUY NO  0.28  outcome=0
        Fay did form (Sep 20) but this is "First Atlantic HURRICANE named Fay"
        — hurricane status means Cat 1+. Fay only reached near-hurricane
        strength before weakening. Fay did NOT reach hurricane status.
        outcome=0 (did not become a hurricane named Fay) = ✓ BUY NO Correct.
        *** LEAVE AS IS ***

id=192  KXFIRSTHURRICANE-26DEC01ATL-GON  BUY NO  0.25  outcome=0
        Gonzalo formed as TS Sep 24. No evidence it reached Cat 1+.
        outcome=0 = ✓ BUY NO Correct. *** LEAVE AS IS ***

id=196  KXFIRSTHURRICANE-26DEC01ATL-HAN  BUY NO  0.25  outcome=0
        Hanna had not formed as of research date.
        outcome=0 = ✓ BUY NO Correct. *** LEAVE AS IS ***

id=201  KXFIRSTHURRICANE-26DEC01ATL-ISA  BUY NO  0.30  outcome=1
        Market: "First Atlantic hurricane — Isaias"
        Isaias is 9th name on the 2026 list. No evidence Isaias formed
        as a hurricane in 2026. outcome=1 appears to be a DATA ERROR.
        → outcome should be 0.
        BUY NO + outcome=0 = ✓ Correct.

id=209  KXBIGBROTHER-26DEC31-DEE  BUY NO  0.24  outcome=0  ← KEEPER
        Devens won, not Dee → outcome=0. BUY NO + 0 = ✓ Correct. OK.

id=210  KXBIGBROTHER-26DEC31-DEE  BUY NO  0.22  outcome=0  → VOID (dup of 209)

id=211  KXBIGBROTHER-26DEC31-YAS  BUY NO  0.22  outcome=0  → VOID (dup of 128)

id=214  KXTRUMPADMINLEAVE-26DEC31-SWIL  BUY NO  0.25  outcome=1
        Susie Wiles departed → outcome=1 (YES).
        BUY NO + outcome=1 = ✗ Incorrect. *** CORRECT — leave as is ***

SUMMARY OF CHANGES THIS SCRIPT MAKES:
  Void duplicates: ids 73, 133, 138, 163, 170, 210, 211
  Fix outcome:     id=201 (Isaias) outcome 1→0

Run from C:\\Users\\qwhit\\AFG\\:
    python3 fix_scorecard_outcomes_v2.py
"""

import sqlite3

DB_PATH = "afg_scorecard.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

print("=" * 68)
print("AFG SCORECARD CORRECTION v2 — November 2026 Audit")
print("=" * 68)

# ── STEP 1: VOID DUPLICATE ROWS ──────────────────────────────────────────────
print("\nSTEP 1: Void duplicate/superseded rows")
print("-" * 50)

VOID_IDS = [
    (73,  "KXBIGBROTHER-26DEC31-DEE  — duplicate (keep id=209)"),
    (133, "KXMLB-26-LAD              — duplicate (keep id=179)"),
    (138, "FEDHIKE-26DEC31 BUY NO    — superseded (keep id=176 BUY YES)"),
    (163, "FEDHIKE-26DEC31 BUY NO    — superseded (keep id=176 BUY YES)"),
    (170, "FEDHIKE-26DEC31 BUY NO    — superseded (keep id=176 BUY YES)"),
    (210, "KXBIGBROTHER-26DEC31-DEE  — duplicate (keep id=209)"),
    (211, "KXBIGBROTHER-26DEC31-YAS  — duplicate (keep id=128)"),
]

for row_id, reason in VOID_IDS:
    cur.execute("SELECT id, ticker, recommendation, outcome, status FROM predictions WHERE id=?", (row_id,))
    row = cur.fetchone()
    if not row:
        print(f"  ⚠  id={row_id} NOT FOUND — skipping")
        continue
    cur.execute("UPDATE predictions SET status='Superseded' WHERE id=?", (row_id,))
    print(f"  VOIDED  id={row_id} | {str(row[1]):<40} | was outcome={row[3]} status={row[4]}")
    print(f"          Reason: {reason}")

conn.commit()
print(f"\n  {len(VOID_IDS)} rows marked Superseded")

# ── STEP 2: FIX OUTCOME ERRORS ───────────────────────────────────────────────
print("\nSTEP 2: Fix outcome errors")
print("-" * 50)

OUTCOME_FIXES = [
    # (id, correct_outcome, note)
    (201, 0, "KXFIRSTHURRICANE-26DEC01ATL-ISA: Isaias did not form/reach Cat1 in 2026"),
]

for row_id, correct_outcome, note in OUTCOME_FIXES:
    cur.execute("""
        SELECT id, ticker, market, recommendation, afg_probability, outcome, status
        FROM predictions WHERE id=?
    """, (row_id,))
    row = cur.fetchone()
    if not row:
        print(f"  ⚠  id={row_id} NOT FOUND — skipping")
        continue

    row_id_, ticker, market, rec, afg_pct, cur_outcome, status = row
    if str(cur_outcome) == str(correct_outcome):
        print(f"  ── id={row_id} already outcome={correct_outcome}, no change needed")
        continue

    cur.execute("UPDATE predictions SET outcome=? WHERE id=?", (correct_outcome, row_id))

    try:
        brier = (float(afg_pct) - correct_outcome) ** 2
        brier_str = f"{brier:.4f}"
    except Exception:
        brier_str = "N/A"

    if rec == "BUY YES":
        verdict = "✓ Correct" if correct_outcome == 1 else "✗ Incorrect"
    else:
        verdict = "✓ Correct" if correct_outcome == 0 else "✗ Incorrect"

    print(f"  FIXED   id={row_id} | {rec} | AFG={afg_pct}")
    print(f"          outcome: {cur_outcome} → {correct_outcome} | {verdict} | Brier={brier_str}")
    print(f"          {note}")

conn.commit()

# ── STEP 3: FINAL SCORECARD TALLY ────────────────────────────────────────────
print("\n" + "=" * 68)
print("FINAL SCORECARD AFTER ALL CORRECTIONS")
print("=" * 68)

cur.execute("""
    SELECT id, ticker, market, recommendation, afg_probability, outcome, category
    FROM predictions
    WHERE outcome IS NOT NULL AND outcome != ''
      AND status NOT IN ('Void','Superseded')
      AND recommendation IN ('BUY YES','BUY NO')
    ORDER BY id
""")
scored = cur.fetchall()

correct = 0
incorrect = 0
total_brier = 0.0
details = []

for row_id, ticker, market, rec, afg_pct, outcome, cat in scored:
    try:
        p = float(afg_pct)
        o = int(outcome)
    except (TypeError, ValueError):
        continue

    brier = (p - o) ** 2
    total_brier += brier

    if (rec == "BUY YES" and o == 1) or (rec == "BUY NO" and o == 0):
        result = "✓ Correct"
        correct += 1
    else:
        result = "✗ Incorrect"
        incorrect += 1

    details.append((row_id, ticker, rec, p, o, brier, result, cat, market))

n = correct + incorrect
accuracy = correct / n * 100 if n else 0
avg_brier = total_brier / n if n else 0

print(f"\n{'ID':<5} {'REC':<10} {'AFG%':<6} {'OUT':<4} {'BRIER':<7} {'RESULT':<14} {'MARKET'}")
print("-" * 90)
for row_id, ticker, rec, p, o, brier, result, cat, market in details:
    mkt = (market or ticker or "")[:55]
    print(f"{row_id:<5} {rec:<10} {p:<6} {o:<4} {brier:<7.4f} {result:<14} {mkt}")

print("-" * 90)
print(f"\n  Total scored : {n}")
print(f"  Correct      : {correct}")
print(f"  Incorrect    : {incorrect}")
print(f"  Accuracy     : {accuracy:.1f}%")
print(f"  Mean Brier   : {avg_brier:.4f}")

conn.close()
print("\nDone. Run 06_build_scorecard.py to regenerate the scorecard.")
