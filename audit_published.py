"""
audit_published.py  --  AFG publication guardrail (added November 12th, 2026)
================================================================================
Audits the page that is about to go public (docs\\index.html) and the posts, and
BLOCKS publication if anything is wrong. Run automatically by run_cycle.py
before the PUSH prompt, and by the git pre-commit hook (install_guardrail.py),
so even a manual "git commit" cannot publish an unaudited scorecard.

WHY IT EXISTS
  On November 12th three errors reached the live scorecard: positions AFG had
  exited were scored as if held; the Market Brier score treated every contract
  as a NO; and a proprietary methodology line was public. verify_afg.py did not
  catch them because it shared the builder's blind spot. This audit does not
  trust the builder. It READS THE PAGE and recomputes every number from the
  database with its own, separate logic.

THE SIX TESTS
  1 HEADLINE NUMBERS  Accuracy, correct, incorrect, scored, excluded, total, AFG
                      Brier and Market Brier on the page equal an independent
                      recomputation from afg_scorecard.db.
  2 EVERY ROW         Each row on the page (contract, call, probabilities,
                      outcome, result) matches the database, and the closed
                      table lists exactly the positions the database says AFG
                      exited before settlement.
  3 CONSERVATION      Total settled = scored + closed = every settled contract in
                      the database. Nothing can silently drop out or be
                      reclassified.
  4 PUBLISHED CALLS   Where data\\price_history.csv has AFG's own published
                      calls, the last call before settlement agrees with whether
                      the database treats the position as closed.
  5 PUBLIC TEXT       Nothing proprietary (see BANNED below) appears on the page
                      or in the Substack post, X post or Note.
  6 CHANGE CONTROL    Compared with the page that is live now (git HEAD), any
                      contract that moved between scored and closed, changed
                      call or result, or disappeared must be documented in
                      scorecard_changes.csv with a reason and a source.

USAGE (from C:\\Users\\qwhit\\AFG\\)
    python3 audit_published.py            exit 0 = safe to publish, 1 = BLOCKED
    python3 audit_published.py --hook     used by the git pre-commit hook
"""
import csv
import datetime as dt
import glob
import html as htmllib
import os
import re
import sqlite3
import subprocess
import sys

DB = "afg_scorecard.db"
PAGE = os.path.join("docs", "index.html")
HISTORY = os.path.join("data", "price_history.csv")
CHANGES = "scorecard_changes.csv"
ACTIVE = "status NOT IN ('Void','Superseded')"

# Proprietary wording that must never appear in public material. Add to this
# list whenever Quentin names something that must stay private.
BANNED = [
    (r"highest[- ]volume", "reveals that markets are screened by trading volume"),
    (r"top[- ](five|5)\b", "reveals the top-five screening rule"),
    (r"\bby volume\b", "reveals that markets are screened by trading volume"),
    (r"categories\s*[x×]\s*5", "reveals the 5-by-5 screening structure"),
    (r"five[- ]category structure", "reveals the screening structure"),
    (r"methodology revised", "internal methodology revision date"),
    (r"revised november", "internal methodology revision date"),
]

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results = []


def check(name, ok, detail=""):
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  {'✓ PASS' if ok else '✗ FAIL'}  {name}")
    if detail:
        for line in str(detail).splitlines():
            print(f"           → {line}")


def warn(name, detail=""):
    results.append((WARN, name, detail))
    print(f"  ⚠ WARN  {name}")
    for line in str(detail).splitlines():
        print(f"           → {line}")


# ── page parsing ──────────────────────────────────────────────────────────────

def _clean(fragment):
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", htmllib.unescape(text)).strip()


def _pct(text):
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m.group(0)) if m else None


def parse_page(page_html):
    """Return the numbers and tables as printed on the page."""
    out = {"stats": {}, "brier": {}, "scored": [], "closed": []}
    for label, value in re.findall(
            r'<div class="stat-label">(.*?)</div>\s*<div class="stat-value">(.*?)</div>', page_html, re.S):
        out["stats"][_clean(label)] = _clean(value)
    for label, value in re.findall(
            r'<div class="label">(.*?)</div>\s*<div class="value">(.*?)</div>', page_html, re.S):
        out["brier"][_clean(label)] = _clean(value)

    sections = re.split(r'<div class="section-title">', page_html)[1:]
    for sec in sections:
        title = _clean(sec.split("</div>", 1)[0])
        body = re.search(r"<tbody>(.*?)</tbody>", sec, re.S)
        if not body:
            continue
        rows = [[_clean(c) for c in re.findall(r"<td>(.*?)</td>", r, re.S)]
                for r in re.findall(r"<tr>(.*?)</tr>", body.group(1), re.S)]
        rows = [r for r in rows if r]
        if title.startswith("All Resolved Forecasts"):
            out["scored"] = rows
        elif title.startswith("Closed Positions"):
            out["closed"] = rows
    out["text"] = _clean(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page_html, flags=re.S))
    return out


# ── independent recomputation from the database ───────────────────────────────

def _date(val):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(str(val).strip(), fmt).date()
        except (ValueError, TypeError):
            pass
    return None


def _p(v):
    v = float(v)
    return v / 100.0 if v > 1.0 else v


def recompute(db_path=DB):
    """Written separately from 06_build_scorecard.py and verify_afg.py on purpose."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tickers = [r[0] for r in conn.execute(
        f"SELECT DISTINCT COALESCE(NULLIF(ticker,''), kalshi_ticker) FROM predictions "
        f"WHERE outcome IN (0,1,'0','1') AND {ACTIVE}")]
    scored, closed = [], []
    for t in sorted(tickers):
        row = conn.execute(
            f"SELECT * FROM predictions WHERE COALESCE(NULLIF(ticker,''), kalshi_ticker)=? "
            f"AND outcome IN (0,1,'0','1') AND {ACTIVE} "
            f"AND recommendation IN ('BUY YES','BUY NO') ORDER BY id DESC LIMIT 1", (t,)).fetchone()
        if row is None:
            continue
        o = int(row["outcome"])
        call = row["recommendation"]
        right = (call == "BUY YES" and o == 1) or (call == "BUY NO" and o == 0)
        c_on, r_on = _date(row["afg_closed_date"]), _date(row["resolution_date"])
        is_closed = bool(row["afg_closed"]) and c_on is not None and (r_on is None or c_on <= r_on)
        item = {"ticker": t, "contract": row["market"], "call": call, "afg": _p(row["afg_probability"]),
                "mkt": _p(row["kalshi_price"]), "outcome": "YES" if o else "NO",
                "o": o, "result": "Correct" if right else "Incorrect", "closed_on": row["afg_closed_date"]}
        (closed if is_closed else scored).append(item)
    conn.close()
    n = len(scored)
    stats = {
        "n": n, "closed": len(closed), "total": n + len(closed),
        "correct": sum(1 for r in scored if r["result"] == "Correct"),
        "afg_brier": sum((r["afg"] - r["o"]) ** 2 for r in scored) / n if n else 0.0,
        "mkt_brier": sum((r["mkt"] - r["o"]) ** 2 for r in scored) / n if n else 0.0,
    }
    stats["incorrect"] = n - stats["correct"]
    stats["accuracy"] = stats["correct"] / n * 100 if n else 0.0
    return scored, closed, stats


# ── the tests ─────────────────────────────────────────────────────────────────

def t1_headline(page, stats):
    s, b = page["stats"], page["brier"]
    problems = []

    def need(label, shown, expected, tol=0.0):
        if shown is None or abs(shown - expected) > tol:
            problems.append(f"{label}: page shows {shown}, database says {expected:g}")
    need("Accuracy %", _pct(s.get("Final-Call Accuracy")), round(stats["accuracy"], 1), 0.051)
    need("Scored", _pct(s.get("Scored")), stats["n"])
    need("Correct", _pct(s.get("Correct")), stats["correct"])
    need("Incorrect", _pct(s.get("Incorrect")), stats["incorrect"])
    need("Excluded", _pct(s.get("Excluded")), stats["closed"])
    need("Total Settled", _pct(s.get("Total Settled")), stats["total"])
    need("AFG Brier", _pct(b.get("AFG Brier Score")), stats["afg_brier"], 0.0015)
    need("Market Brier", _pct(b.get("Market (Kalshi) Brier Score")), stats["mkt_brier"], 0.0015)
    check("Headline numbers equal an independent recomputation", not problems,
          "\n".join(problems) if problems else
          f"{stats['correct']}/{stats['n']} = {stats['accuracy']:.1f}%  |  AFG Brier {stats['afg_brier']:.3f}  |  "
          f"Market Brier {stats['mkt_brier']:.3f}  |  {stats['closed']} closed")


def t2_rows(page, scored, closed):
    problems = []

    def key(contract, call, result):
        return (contract, call, result)

    page_scored = {}
    for r in page["scored"]:
        if len(r) < 9:
            problems.append(f"malformed scored row: {r}")
            continue
        call = "BUY YES" if "BUY YES" in r[3] else "BUY NO" if "BUY NO" in r[3] else r[3]
        res = "Correct" if "Correct" in r[7] and "Incorrect" not in r[7] else "Incorrect"
        page_scored[r[1]] = (call, res, _pct(r[4]), _pct(r[5]), r[6].upper())
    db_scored = {r["contract"]: r for r in scored}
    for c in sorted(set(db_scored) | set(page_scored)):
        if c not in page_scored:
            problems.append(f"missing from the scored table: {c}")
        elif c not in db_scored:
            problems.append(f"on the scored table but not scored in the database: {c}")
        else:
            d, p = db_scored[c], page_scored[c]
            if (p[0], p[1]) != (d["call"], d["result"]):
                problems.append(f"{c}: page {p[0]}/{p[1]}, database {d['call']}/{d['result']}")
            if p[2] is None or abs(p[2] - d["afg"] * 100) > 0.51 or p[3] is None or abs(p[3] - d["mkt"] * 100) > 0.51:
                problems.append(f"{c}: probabilities differ (page {p[2]}/{p[3]}, database "
                                f"{d['afg'] * 100:.0f}/{d['mkt'] * 100:.0f})")
            if p[4] not in (d["outcome"],):
                problems.append(f"{c}: Settled column shows '{p[4]}', outcome is {d['outcome']}")

    page_closed = {r[1] for r in page["closed"] if len(r) >= 2}
    db_closed = {r["contract"] for r in closed}
    for c in sorted(db_closed - page_closed):
        problems.append(f"AFG exited this position before settlement but it is not in the closed table: {c}")
    for c in sorted(page_closed - db_closed):
        problems.append(f"in the closed table but the database does not show a pre-settlement exit: {c}")
    if len(page["scored"]) != len(page_scored):
        problems.append("duplicate contract titles in the scored table")
    check("Every row on the page matches the database", not problems,
          "\n".join(problems[:12]) + (f"\n(+{len(problems) - 12} more)" if len(problems) > 12 else "")
          if problems else f"{len(page['scored'])} scored rows and {len(page['closed'])} closed rows checked")


def t3_conservation(page, stats):
    total_page = _pct(page["stats"].get("Total Settled"))
    shown = len(page["scored"]) + len(page["closed"])
    problems = []
    if total_page != stats["total"]:
        problems.append(f"page says {total_page if total_page is None else format(total_page, 'g')} settled; database has {stats['total']} settled contracts")
    if shown != stats["total"]:
        problems.append(f"page tables list {shown} contracts; database has {stats['total']} settled contracts")
    if stats["n"] + stats["closed"] != stats["total"]:
        problems.append("scored + closed does not equal total settled")
    check("Every settled contract is either scored or disclosed (nothing dropped)", not problems,
          "\n".join(problems) if problems else
          f"{stats['total']} settled = {stats['n']} scored + {stats['closed']} closed")


def t4_published_calls(scored, closed):
    if not os.path.exists(HISTORY):
        warn("Published-calls cross-check skipped", f"{HISTORY} not found")
        return
    last = {}
    with open(HISTORY, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            d = _date(r.get("log_date"))
            if d:
                last.setdefault(r["kalshi_ticker"], []).append((d, r["recommendation"].upper()))
    conn = sqlite3.connect(DB)
    res = {r[0]: _date(r[1]) for r in conn.execute(
        f"SELECT COALESCE(NULLIF(ticker,''), kalshi_ticker), MAX(resolution_date) FROM predictions "
        f"WHERE outcome IN (0,1,'0','1') AND {ACTIVE} GROUP BY 1")}
    conn.close()
    closed_t = {r["ticker"] for r in closed}
    problems, checked = [], 0
    for r in scored + closed:
        t = r["ticker"]
        calls = sorted(c for c in last.get(t, []) if res.get(t) is None or c[0] <= res[t])
        if not calls:
            continue
        checked += 1
        published_exit = "NO TRADE" in calls[-1][1]
        if published_exit and t not in closed_t:
            problems.append(f"{t}: AFG's last published call on {calls[-1][0]} was NO TRADE, "
                            f"but the page scores it as a live call")
        if not published_exit and t in closed_t:
            problems.append(f"{t}: the database says AFG exited, but its last published call on "
                            f"{calls[-1][0]} was {calls[-1][1]}")
    check("Closures agree with AFG's own published calls", not problems,
          "\n".join(problems) if problems else
          f"{checked} settled contract(s) have published-call history (the rest settled before it began)")


def t5_public_text(page):
    today = dt.date.today().isoformat()
    files = {PAGE: page["text"]}
    for pattern in (f"reports/AFG_Substack_Post_{today}.md", f"reports/AFG_Twitter_Post_{today}.txt",
                    f"reports/AFG_Substack_Note_{today}.txt",
                    f"reports/scorecards/AFG_Resolution_Post_{today}.txt"):
        for f in glob.glob(pattern):
            files[f] = open(f, encoding="utf-8", errors="replace").read()
    problems = []
    for f, text in files.items():
        for rx, why in BANNED:
            m = re.search(rx, text, re.I)
            if m:
                problems.append(f"{f}: \"{m.group(0)}\" ({why})")
    check("No proprietary wording in public material", not problems,
          "\n".join(problems) if problems else f"{len(files)} public file(s) scanned")
    # The paid report is not public, so this is a warning until Quentin decides.
    rep = f"reports/AFG_Research_Report_{today}.docx"
    if os.path.exists(rep):
        try:
            import docx
            d = docx.Document(rep)
            text = "\n".join([p.text for p in d.paragraphs] +
                             [c.text for t in d.tables for row in t.rows for c in row.cells])
            hits = sorted({m.group(0) for rx, _ in BANNED for m in [re.search(rx, text, re.I)] if m})
            if hits:
                warn("Paid report contains screening wording", f"{rep}: {hits}")
        except Exception:
            pass


def _git(*args):
    try:
        p = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
        return p.returncode, p.stdout
    except Exception:
        return 1, ""


def load_changes():
    docs = {}
    if os.path.exists(CHANGES):
        with open(CHANGES, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c, ch = (r.get("contract") or "").strip(), (r.get("change") or "").strip()
                if c and ch and (r.get("reason") or "").strip() and (r.get("source") or "").strip():
                    docs[(c, ch)] = r
    return docs


def t6_change_control(page):
    code, old_html = _git("show", f"HEAD:{PAGE.replace(os.sep, '/')}")
    if code != 0 or not old_html.strip():
        warn("Change control skipped", "no previously published page found in git (first publication?)")
        return
    old = parse_page(old_html)

    def classify(p):
        sc, cl = {}, set()
        for r in p["scored"]:
            if len(r) >= 8:
                call = "BUY YES" if "BUY YES" in r[3] else "BUY NO"
                sc[r[1]] = (call, "Correct" if "Correct" in r[7] and "Incorrect" not in r[7] else "Incorrect")
        for r in p["closed"]:
            if len(r) >= 2:
                cl.add(r[1])
        return sc, cl
    o_sc, o_cl = classify(old)
    n_sc, n_cl = classify(page)
    changes = []
    for c, (call, res) in o_sc.items():
        if c in n_cl:
            changes.append((c, "moved_to_closed", f"was scored ({call}, {res})"))
        elif c not in n_sc:
            changes.append((c, "removed", "was scored on the live page"))
        else:
            if n_sc[c][0] != call:
                changes.append((c, "call_changed", f"{call} -> {n_sc[c][0]}"))
            if n_sc[c][1] != res:
                changes.append((c, "result_changed", f"{res} -> {n_sc[c][1]}"))
    for c in o_cl:
        if c in n_sc:
            changes.append((c, "moved_to_scored", "was in the closed table on the live page"))
        elif c not in n_cl:
            changes.append((c, "removed", "was in the closed table on the live page"))
    added = (set(n_sc) | n_cl) - (set(o_sc) | o_cl)
    docs = load_changes()
    undocumented = [x for x in changes if (x[0], x[1]) not in docs]
    if undocumented:
        lines = [f"{c}  [{ch}]  {why}" for c, ch, why in undocumented]
        lines.append(f"Document each in {CHANGES} (columns: contract,change,reason,source,date), then rerun.")
        check("Changes to the published record are documented", False, "\n".join(lines))
    else:
        check("Changes to the published record are documented", True,
              f"{len(changes)} reclassification(s) documented; {len(added)} newly settled contract(s) added")


def run(hook=False):
    if hook:
        code, staged = _git("diff", "--cached", "--name-only")
        if PAGE.replace(os.sep, "/") not in staged.split():
            return 0
    for p in (DB, PAGE):
        if not os.path.exists(p):
            print(f"STOPPED: {p} not found -- run from C:\\Users\\qwhit\\AFG\\ after building the scorecard.")
            return 1
    print("=" * 66)
    print(f"AFG PUBLICATION AUDIT -- {dt.date.today()}")
    print("=" * 66)
    scored, closed, stats = recompute()
    print()
    try:
        page = parse_page(open(PAGE, encoding="utf-8").read())
        if not page["scored"]:
            raise ValueError("no scored-positions table found on the page")
    except Exception as e:
        check("The page can be read", False, f"{PAGE}: {e}")
        print("\nBLOCKED: the page is empty or unreadable. Do NOT publish.")
        return 1
    for fn, args in ((t1_headline, (page, stats)), (t2_rows, (page, scored, closed)),
                     (t3_conservation, (page, stats)), (t4_published_calls, (scored, closed)),
                     (t5_public_text, (page,)), (t6_change_control, (page,))):
        try:
            fn(*args)
        except Exception as e:      # an audit that crashes must fail closed, never pass
            check(f"{fn.__name__} ran", False, f"audit error: {type(e).__name__}: {e}")
    failed = [r for r in results if r[0] == FAIL]
    print("\n" + "=" * 66)
    if failed:
        print(f"BLOCKED: {len(failed)} test(s) failed. Do NOT publish. Send this output to Claude.")
        print("=" * 66)
        return 1
    print("ALL TESTS PASSED. Safe to publish.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(run(hook="--hook" in sys.argv))
