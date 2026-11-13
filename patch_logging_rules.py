"""
patch_logging_rules.py  --  November 11th, 2026
================================================================================
Fixes afg_logging_rules.py so the scorecard's Brier score uses the FINAL
published call on every open position.

THE PROBLEM
  Rule 5 said "same direction logs nothing", so when AFG repriced a call in the
  same direction (Wiles: BUY NO at 25%, later BUY NO at 38%) the database kept
  the first probability. Accuracy was never affected, but Brier was.

THE FIX (rule 5b)
  Same-direction repeat: no new row, but the open row's afg_probability,
  kalshi_price, edge_score and conviction are refreshed to the latest published
  call. Direction, report_date (the first-call date) and every resolved row are
  untouched. New rows now also write `ticker`, so Check 3 no longer depends on
  the backfill.

SAFE TO RUN
  * backs up afg_logging_rules.py first
  * refuses to patch if the file is not the expected version
  * refuses to patch twice
  * compiles the result and restores the backup if that fails

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 patch_logging_rules.py
"""
import py_compile
import shutil
import sys

PATH = "afg_logging_rules.py"
MARKER = "RULE 5b"

raw = open(PATH, "rb").read().decode("utf-8")
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")

if MARKER in text:
    print("Already patched. Nothing to do.")
    sys.exit(0)

EDITS = [
    # 1. docstring
    ("""  5. SAME DIRECTION Repeating an existing open call logs nothing new.
""",
     """  5. SAME DIRECTION Repeating an existing open call adds no new row. RULE 5b:
                    the open row is refreshed to the latest published
                    probability and Kalshi price (direction and first-call
                    date unchanged) so Brier uses the final call.
"""),

    # 2. _insert writes `ticker`
    ("""           (market, category, kalshi_ticker, report_date, kalshi_price,
            afg_probability, edge_score, conviction, recommendation,
            contract_close_date, status, afg_closed)
           VALUES (?,?,?,?,?,?,?,?,?,?, 'Open', 0)\"\"\",
        (r["market"], r["category"], ticker, report_date, kal_p, afg_p,
""",
     """           (market, category, kalshi_ticker, ticker, report_date, kalshi_price,
            afg_probability, edge_score, conviction, recommendation,
            contract_close_date, status, afg_closed)
           VALUES (?,?,?,?,?,?,?,?,?,?,?, 'Open', 0)\"\"\",
        (r["market"], r["category"], ticker, ticker, report_date, kal_p, afg_p,
"""),

    # 3. rule 5b
    ("""            # else rule 5: same direction, nothing new
""",
     """            else:
                # RULE 5b: same direction. No new row; refresh the open row to
                # the latest published call so Brier scores the final call.
                afg_p = float(r["afg_probability"])
                kal_p = float(r["kalshi_price"])
                cur = conn.execute(
                    "SELECT afg_probability, kalshi_price FROM predictions WHERE id=?",
                    (latest["id"],)).fetchone()
                if (cur is not None and latest["status"] == "Open"
                        and (abs(float(cur[0]) - afg_p) > 1e-9
                             or abs(float(cur[1]) - kal_p) > 1e-9)):
                    conn.execute(
                        "UPDATE predictions SET afg_probability=?, kalshi_price=?, "
                        "edge_score=?, conviction=?, "
                        "ticker=COALESCE(NULLIF(ticker, ''), ?) WHERE id=?",
                        (afg_p, kal_p, round(afg_p - kal_p, 4), r["conviction"],
                         ticker, latest["id"]))
                    conn.commit()
                    print(f"  reprice  {ticker}: {rec} "
                          f"{float(cur[0]):.0%}/{float(cur[1]):.0%} -> "
                          f"{afg_p:.0%}/{kal_p:.0%}  (row {latest['id']})")
"""),
]

for old, new in EDITS:
    n = text.count(old)
    if n != 1:
        sys.exit(f"STOPPED: expected text found {n} times (needed exactly 1). "
                 f"The file is not the version I patched. Nothing was changed.\n"
                 f"First line of the block I could not find:\n{old.splitlines()[0]}")
    text = text.replace(old, new)

backup = PATH + ".bak_2026-11-11"
shutil.copyfile(PATH, backup)
out = text.replace("\n", "\r\n") if crlf else text
with open(PATH, "wb") as fh:
    fh.write(out.encode("utf-8"))

try:
    py_compile.compile(PATH, doraise=True)
except py_compile.PyCompileError as e:
    shutil.copyfile(backup, PATH)
    sys.exit(f"STOPPED: patched file did not compile ({e}). Original restored.")

print(f"Patched {PATH}. Backup: {backup}")
print("Rule 5b is live: same-direction repricings now update the open row.")
