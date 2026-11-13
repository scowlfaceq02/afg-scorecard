"""
post_mortem.py  --  AFG settlement post-mortems (added November 12th, 2026)
================================================================================
Superforecaster Commandments 7, 8 and 10: track results, review the reasoning
that was written down at forecast time, and review wins as rigorously as losses
(a right call for a wrong reason is luck, and luck does not repeat).

For every newly settled position this writes one sheet to
reports\\post_mortems\\post_mortem_<date>.md containing:
  * the final call, the outcome, and AFG vs Kalshi Brier
  * a classification (below)
  * the reasoning journaled at the time (final call and first call), verbatim
  * the five review questions, blank, to be answered
  * a record-wide section: accuracy and Brier by direction and by category

CLASSIFICATION
  RIGHT, BEAT MARKET     skill candidate: check the reason was the right one
  RIGHT, LOST TO MARKET  right side, but the market was better calibrated
  WRONG, BEAT MARKET     near miss or bad luck: check the reasoning held up
  WRONG, LOST TO MARKET  process error candidate: review first

Each position is reviewed once (tracked in table `post_mortem_done`). Positions
settled before the journal began have no recorded reasoning and say so; no
reasoning is ever reconstructed after the fact.

Read-only on `predictions` and `call_journal`.

    python3 post_mortem.py            newly settled positions only
    python3 post_mortem.py --all      every settled position (re-review)
"""
import datetime as dt
import os
import sqlite3
import sys
from collections import defaultdict

DB = "afg_scorecard.db"
OUT_DIR = os.path.join("reports", "post_mortems")
ACTIVE = "status NOT IN ('Void','Superseded')"


def direction(rec):
    r = str(rec or "").upper()
    return "BUY YES" if "BUY YES" in r else "BUY NO" if "BUY NO" in r else "NO TRADE"


def scored_positions(conn):
    """Latest BUY row per ticker among resolved rows (the final-call rule)."""
    rows = conn.execute(
        f"SELECT id, COALESCE(NULLIF(ticker,''), kalshi_ticker) AS t, market, category, "
        f"recommendation, afg_probability, kalshi_price, outcome, resolution_date "
        f"FROM predictions WHERE outcome IN (0,1,'0','1') AND {ACTIVE} ORDER BY id").fetchall()
    final = {}
    for r in rows:
        if direction(r["recommendation"]) != "NO TRADE":
            final[r["t"]] = r
    return list(final.values())


def evaluate(r):
    o = int(r["outcome"])
    d = direction(r["recommendation"])
    p, m = float(r["afg_probability"]), float(r["kalshi_price"])
    correct = (d == "BUY YES" and o == 1) or (d == "BUY NO" and o == 0)
    b_afg, b_mkt = (p - o) ** 2, (m - o) ** 2
    beat = b_afg < b_mkt
    label = ("RIGHT" if correct else "WRONG") + (", BEAT MARKET" if beat else ", LOST TO MARKET")
    return d, o, p, m, correct, b_afg, b_mkt, label


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS post_mortem_done (ticker TEXT PRIMARY KEY, done_date TEXT)")
    journal = conn.execute("SELECT name FROM sqlite_master WHERE name='call_journal'").fetchone() is not None
    done = {r[0] for r in conn.execute("SELECT ticker FROM post_mortem_done")}
    everything = "--all" in sys.argv

    allpos = scored_positions(conn)
    todo = [r for r in allpos if everything or r["t"] not in done]
    today = dt.date.today().isoformat()

    if not todo:
        print("  post-mortems: no newly settled positions to review.")
        conn.close()
        return 0

    def entries(t):
        if not journal:
            return None, None
        rows = conn.execute("SELECT * FROM call_journal WHERE kalshi_ticker=? "
                            "AND recommendation != 'NO TRADE' ORDER BY report_date, id", (t,)).fetchall()
        return (rows[0], rows[-1]) if rows else (None, None)

    lines = [f"# AFG Post-Mortems -- {today}", "",
             "Review each position before the next cycle. Answer the five questions in writing. "
             "A win is reviewed as hard as a loss: was AFG right for the reasons it gave, or lucky?", ""]
    order = {"WRONG, LOST TO MARKET": 0, "WRONG, BEAT MARKET": 1, "RIGHT, LOST TO MARKET": 2, "RIGHT, BEAT MARKET": 3}
    evald = sorted(((r, evaluate(r)) for r in todo), key=lambda x: order[x[1][7]])
    for r, (d, o, p, m, correct, b_afg, b_mkt, label) in evald:
        first, last = entries(r["t"])
        lines += [f"## {r['market']}  ({r['t']})", "",
                  f"- **Classification:** {label}",
                  f"- **Final call:** {d} | AFG probability of YES {p:.0%} | Kalshi {m:.0%} | "
                  f"outcome {'YES' if o else 'NO'} | settled {r['resolution_date'] or 'n/a'}",
                  f"- **Brier:** AFG {b_afg:.3f} vs Kalshi {b_mkt:.3f} "
                  f"({'AFG better' if b_afg < b_mkt else 'Kalshi better'})"]
        if last is None:
            lines += ["- **Reasoning at forecast time:** none recorded (this call predates the journal; "
                      "no reasoning is reconstructed after the fact)"]
        else:
            lines += [f"- **Final-call reasoning ({last['report_date']}, {last['recommendation']} "
                      f"{last['afg_probability']:.0%} vs {last['kalshi_price']:.0%}):**",
                      f"  - Outside view: {last['outside_view']}",
                      f"  - Rationale: {last['rationale']}",
                      f"  - Counterargument: {last['counterargument']}"]
            if first["id"] != last["id"]:
                lines += [f"- **First-call reasoning ({first['report_date']}, {first['recommendation']} "
                          f"{first['afg_probability']:.0%} vs {first['kalshi_price']:.0%}):**",
                          f"  - Rationale: {first['rationale']}"]
        lines += ["", "Review (answer in writing):",
                  "1. Why did I believe this?", "2. What evidence mattered most?",
                  "3. What did I miss?", "4. Was I lucky?", "5. Was I actually right?", ""]

    # record-wide calibration
    by_dir, by_cat = defaultdict(list), defaultdict(list)
    for r in allpos:
        e = evaluate(r)
        by_dir[e[0]].append(e)
        by_cat[r["category"]].append(e)

    def table(title, groups):
        out = [f"### {title}", "", "| Group | Scored | Correct | Accuracy | AFG Brier | Kalshi Brier |",
               "|---|---|---|---|---|---|"]
        for k in sorted(groups, key=str):
            g = groups[k]
            c = sum(1 for e in g if e[4])
            out.append(f"| {k} | {len(g)} | {c} | {c / len(g):.0%} | "
                       f"{sum(e[5] for e in g) / len(g):.3f} | {sum(e[6] for e in g) / len(g):.3f} |")
        return out + [""]

    lines += ["## Record-wide calibration (all settled positions)", ""]
    lines += table("By direction", by_dir) + table("By category", by_cat)
    tot = [evaluate(r) for r in allpos]
    lines += [f"Overall: {sum(1 for e in tot if e[4])}/{len(tot)} correct; "
              f"AFG Brier {sum(e[5] for e in tot) / len(tot):.3f} vs "
              f"Kalshi {sum(e[6] for e in tot) / len(tot):.3f}.", ""]

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"post_mortem_{today}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    for r in todo:
        conn.execute("INSERT OR REPLACE INTO post_mortem_done VALUES (?,?)", (r["t"], today))
    conn.commit()
    conn.close()
    print(f"  post-mortems: {len(todo)} position(s) written to {path}")
    return 0


if __name__ == "__main__":
    if not os.path.exists(DB):
        sys.exit(f"{DB} not found -- run from C:\\Users\\qwhit\\AFG\\")
    sys.exit(main())
