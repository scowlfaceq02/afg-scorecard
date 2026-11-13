"""
test_scorecard_rules.py  --  scorecard regression tests (added November 12th, 2026)
================================================================================
Proves, on a throwaway fixture database (your real data is never touched), that:

  A. The scorecard builder follows AFG's published scoring rules:
       * final call only (the latest BUY YES / BUY NO row)
       * a position AFG exited before settlement is EXCLUDED and disclosed, never scored
       * an exit dated after settlement does not exclude a position
       * Void / Superseded rows are invisible
       * outcomes print as YES/NO, and the Market Brier score uses the real outcomes
       * no proprietary wording appears on the page
  B. audit_published.py would have CAUGHT each failure that reached the live
     scorecard on November 12th, 2026 (closed positions scored, a wrong Market
     Brier, public methodology wording, a silent reclassification).

run_cycle.py runs this before every cycle. If a script change ever breaks a
rule, the cycle stops BEFORE anything is built or published.

    python3 test_scorecard_rules.py       exit 0 = all rules hold
"""
import importlib.util
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


builder = _load("scorecard_builder", "06_build_scorecard.py")
audit = _load("audit_published", "audit_published.py")

failures = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def make_db(path):
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE predictions (id INTEGER PRIMARY KEY, ticker TEXT, kalshi_ticker TEXT, market TEXT,
        category TEXT, recommendation TEXT, afg_probability REAL, kalshi_price REAL, published_date TEXT,
        close_date TEXT, resolution_date TEXT, outcome INTEGER, status TEXT, afg_closed INTEGER DEFAULT 0,
        afg_closed_date TEXT, afg_closed_reason TEXT)""")

    def ins(i, t, name, cat, rec, p, m, pub, close, res, out, status, cl=0, cd=None):
        c.execute("INSERT INTO predictions (id,ticker,kalshi_ticker,market,category,recommendation,afg_probability,"
                  "kalshi_price,published_date,close_date,resolution_date,outcome,status,afg_closed,afg_closed_date,"
                  "afg_closed_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (i, t, t, name, cat, rec, p, m, pub, close, res, out, status, cl, cd,
                   f"AFG published NO TRADE on {cd}" if cl else None))
    # six positions AFG exited before settlement (real rows from the database)
    ins(9, "FEDHIKE", "Next Fed rate hike", "Economics", "BUY NO", .45, .62, "2026-07-21", "2026-09-11", "2026-09-11", None, "Superseded", 1, "2026-09-11")
    ins(176, "FEDHIKE", "Next Fed rate hike", "Economics", "BUY YES", .80, .77, "2026-08-31", "2026-09-11", "2026-09-11", 1, "Resolved", 1, "2026-09-11")
    ins(110, "ALC", "US Open Alcaraz", "Sports", "BUY YES", .33, .29, "2026-08-31", "2026-09-13", "2026-09-02", None, "Superseded", 1, "2026-09-02")
    ins(175, "ALC", "US Open Alcaraz", "Sports", "BUY YES", .33, .29, "2026-08-31", "2026-09-13", "2026-09-13", 0, "Resolved", 1, "2026-09-02")
    ins(97, "FEDSEP", "Fed September", "Economics", "BUY YES", .76, .64, "2026-08-07", "2026-08-31", "2026-08-31", 0, "Resolved", 1, "2026-08-31")
    ins(201, "ISA", "Isaias", "Weather", "BUY NO", .30, .37, "2026-09-28", "2026-10-07", "2026-10-07", 1, "Resolved", 1, "2026-10-07")
    ins(159, "HMONTH", "Hottest July", "Weather", "BUY YES", .24, .16, "2026-08-10", "2026-08-12", "2026-08-12", 0, "Resolved", 1, "2026-08-12")
    ins(186, "HURMAJ", "Major hurricanes", "Weather", "BUY NO", .22, .32, "2026-09-16", "2026-10-07", "2026-10-07", 1, "Resolved", 1, "2026-10-07")
    # scored positions: a reversal (final call must be the later row), Bayesian updating, a void duplicate
    ins(300, "REV", "Reversed call", "Sports", "BUY NO", .30, .40, "2026-09-01", "2026-10-20", "2026-10-20", 1, "Resolved")
    ins(301, "REV", "Reversed call", "Sports", "BUY YES", .60, .50, "2026-10-01", "2026-10-20", "2026-10-20", 1, "Resolved")
    ins(302, "VOIDED", "Void duplicate", "Sports", "BUY NO", .20, .30, "2026-09-01", "2026-10-20", "2026-10-20", 0, "Void")
    ins(303, "LATE", "Exit logged after settlement", "Sports", "BUY NO", .30, .40, "2026-09-20", "2026-10-20", "2026-10-20", 0, "Resolved", 1, "2026-10-25")
    for i in range(10):          # BUY NO, half the outcomes are YES (this is what exposes a wrong Market Brier)
        ins(400 + i, f"OTH{i}", f"Other {i}", "Politics", "BUY NO", .30, .40, "2026-09-20", "2026-10-20", "2026-10-20", i % 2, "Resolved")
    c.commit()
    return c


tmp = tempfile.mkdtemp(prefix="afg_rules_")
try:
    db = os.path.join(tmp, "afg_scorecard.db")
    conn = make_db(db)
    print("A. The builder follows the scoring rules\n")
    scored, closed = builder.fetch_scored_positions(conn)
    stats = builder.compute_stats(scored)
    by_t = {r["ticker"]: r for r in scored}
    closed_t = {r["ticker"] for r in closed}

    check("six positions exited before settlement are excluded and disclosed",
          closed_t == {"FEDHIKE", "ALC", "FEDSEP", "ISA", "HMONTH", "HURMAJ"}, str(sorted(closed_t)))
    check("none of them is scored", not (closed_t & set(by_t)))
    check("an exit dated AFTER settlement does not exclude the position", "LATE" in by_t)
    check("final call is the latest BUY row (reversal scored as BUY YES)", by_t["REV"]["final_call"] == "BUY YES")
    check("Void rows are invisible", "VOIDED" not in by_t and "VOIDED" not in closed_t)
    n_settled = conn.execute("SELECT COUNT(DISTINCT ticker) FROM predictions WHERE outcome IN (0,1) AND status NOT IN ('Void','Superseded')").fetchone()[0]
    check("conservation: scored + closed = every settled contract", len(scored) + len(closed) == n_settled,
          f"{len(scored)} + {len(closed)} vs {n_settled}")
    check("outcomes are YES/NO text", all(r["outcome"] in ("YES", "NO") for r in scored + closed))
    # exact expected Market Brier, worked by hand from the fixture
    exp = {"REV": (.50, 1), "LATE": (.40, 0)}
    exp_m = [(exp["REV"][0] - exp["REV"][1]) ** 2, (exp["LATE"][0] - exp["LATE"][1]) ** 2] + \
            [(.40 - (i % 2)) ** 2 for i in range(10)]
    check("Market Brier uses the real outcomes (not all-NO)",
          abs(stats["mkt_brier"] - sum(exp_m) / len(exp_m)) < 1e-3,
          f"got {stats['mkt_brier']:.4f}, expected {sum(exp_m) / len(exp_m):.4f}")

    html = builder.build_html(scored, closed, stats, "November 12, 2026")
    page = audit.parse_page(html)
    sc, cl, st = audit.recompute(db)
    audit.results.clear()
    audit.t1_headline(page, st)
    audit.t2_rows(page, sc, cl)
    audit.t3_conservation(page, st)
    check("the page the builder writes passes audit tests 1-3", all(r[0] == audit.PASS for r in audit.results),
          str([r for r in audit.results if r[0] != audit.PASS]))
    audit.results.clear()
    audit.t5_public_text(page)
    check("no proprietary wording on the page (test 5)", all(r[0] != audit.FAIL for r in audit.results))

    print("\nB. The audit catches the failures that reached the live site\n")
    # 1. closed positions scored as if held (the Nov 9-12 failure)
    old_scored = scored + closed
    for r in closed:
        r["result"] = "Correct" if r["would_have"].endswith("Correct") and "Incorrect" not in r["would_have"] else "Incorrect"
    bad1 = builder.build_html(old_scored, [], builder.compute_stats(old_scored), "x")
    audit.results.clear()
    p1 = audit.parse_page(bad1)
    audit.t1_headline(p1, st); audit.t2_rows(p1, sc, cl); audit.t3_conservation(p1, st)
    check("catches closed positions being scored as if held", any(r[0] == audit.FAIL for r in audit.results))

    # 2. wrong Market Brier (outcome compared to text 'YES' when it is 1/0)
    bad2 = re.sub(r'(Market \(Kalshi\) Brier Score</div>\s*<div class="value">)[\d.]+', r"\g<1>0.189", html)
    audit.results.clear(); audit.t1_headline(audit.parse_page(bad2), st)
    check("catches a wrong Market Brier score", any(r[0] == audit.FAIL for r in audit.results))

    # 3. a headline number that disagrees with the table
    bad3 = re.sub(r'(Final-Call Accuracy</div>\s*<div class="stat-value">)[\d.]+', r"\g<1>99.9", html)
    audit.results.clear(); audit.t1_headline(audit.parse_page(bad3), st)
    check("catches a wrong headline accuracy", any(r[0] == audit.FAIL for r in audit.results))

    # 4. a settled contract silently dropped from the page
    bad4 = re.sub(r"<tr>\s*<td>1</td>.*?</tr>", "", html, count=1, flags=re.S)
    audit.results.clear(); p4 = audit.parse_page(bad4)
    audit.t2_rows(p4, sc, cl); audit.t3_conservation(p4, st)
    check("catches a settled contract disappearing from the page", any(r[0] == audit.FAIL for r in audit.results))

    # 5. proprietary wording
    bad5 = html.replace("AFG publishes research every",
                        "Each cycle covers the top five highest-volume Kalshi markets. AFG publishes research every")
    audit.results.clear(); audit.t5_public_text(audit.parse_page(bad5))
    check("catches proprietary screening wording", any(r[0] == audit.FAIL for r in audit.results))
    bad5b = html.replace("AFG is scored on", "Scoring methodology revised November 6th, 2026. AFG is scored on")
    audit.results.clear(); audit.t5_public_text(audit.parse_page(bad5b))
    check("catches the methodology revision date", any(r[0] == audit.FAIL for r in audit.results))

    # 6. silent reclassification against the live page (real git repo in a temp folder)
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "docs"))
    cwd = os.getcwd()
    try:
        os.chdir(repo)
        g = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True)
        g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        open("docs/index.html", "w", encoding="utf-8").write(bad1)         # the old live page: closed ones scored
        g("add", "-A"); g("commit", "-q", "-m", "live")
        audit.results.clear(); audit.t6_change_control(page)               # new page: six moved to closed
        check("catches positions silently moved from scored to closed",
              any(r[0] == audit.FAIL for r in audit.results))
        names = [r["market"] for r in closed]
        with open("scorecard_changes.csv", "w", encoding="utf-8", newline="") as fh:
            fh.write("contract,change,reason,source,date\n")
            for n in names:
                fh.write(f"{n},moved_to_closed,exit recorded before settlement,afg_scorecard.db,2026-11-12\n")
        audit.results.clear(); audit.t6_change_control(page)
        check("accepts the same moves once each is documented with a reason and source",
              all(r[0] != audit.FAIL for r in audit.results), str(audit.results))
        with open("scorecard_changes.csv", "w", encoding="utf-8", newline="") as fh:
            fh.write("contract,change,reason,source,date\n")
            for n in names:
                fh.write(f"{n},moved_to_closed,,,2026-11-12\n")
        audit.results.clear(); audit.t6_change_control(page)
        check("rejects documentation with no reason or source", any(r[0] == audit.FAIL for r in audit.results))
    finally:
        os.chdir(cwd)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} RULE TEST(S) FAILED:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("ALL SCORECARD RULES HOLD.")
