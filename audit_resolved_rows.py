"""
audit_resolved_rows.py — READ-ONLY check that every RESOLVED contract in
afg_scorecard.db carries exactly the calls AFG published.

WHY: on 12 Oct 2026 the Blanche (next Attorney General) contract was found
scoring AFG's 7 August BUY YES as the first call, although AFG first
published BUY NO on 31 July — a published loss counted as a win on the
First-Call track. Contracts that resolved BEFORE the October backfill were
skipped by it ("resolved rows are never touched"), so their rows still
reflect older hand fixes and the July duplicate cleanup.

WHAT IT DOES: replays every published cycle in afg_backfill_history.csv
through the current logging rules into a temporary database, then compares,
for every contract that is Resolved in the real database:
  - the live rows (date, call, AFG %, Kalshi %) — expected vs actual
  - the closed-position flag
  - which call the First-Call and Updated-Position tracks score, and
    whether that call was correct — expected vs actual

NOTHING IS WRITTEN to afg_scorecard.db (opened read-only). Output is printed
and saved to reports/resolved_audit_<today>.txt — attach that file in chat.

Run from C:\\Users\\qwhit\\AFG:
    python3 audit_resolved_rows.py
"""

import datetime
import os
import sqlite3
import tempfile

import pandas as pd

import db
import afg_logging_rules as R

HISTORY_CSV = "afg_backfill_history.csv"
EXCLUDED_DATES = {"2026-07-18", "2026-09-07"}   # not published


def replay():
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "expected.db")
    real = db.DB_PATH
    db.DB_PATH = path
    try:
        db.init_db()
    finally:
        db.DB_PATH = real
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    R.ensure_columns(conn)
    h = pd.read_csv(HISTORY_CSV)
    h["report_date"] = h["report_date"].astype(str).map(R.iso)
    h = h[~h["report_date"].isin(EXCLUDED_DATES)]
    for d, g in sorted(h.groupby("report_date"), key=lambda x: x[0]):
        R.process_cycle(conn, d, g.to_dict("records"), [])
    conn.commit()
    return conn


def rows_for(conn, ticker, live_only=True):
    q = ("SELECT id, report_date, recommendation, afg_probability, kalshi_price, status, "
         "COALESCE(afg_closed,0) AS closed, afg_closed_date FROM predictions WHERE kalshi_ticker=?")
    if live_only:
        q += " AND status IN ('Open','Resolved')"
    return [dict(r) for r in conn.execute(q + " ORDER BY report_date, id", (ticker,)).fetchall()]


def sig(r):
    return (R.iso(r["report_date"]), r["recommendation"],
            round(float(r["afg_probability"]), 3), round(float(r["kalshi_price"]), 3))


def correct(rec, outcome):
    return (rec == "BUY YES" and outcome == 1) or (rec == "BUY NO" and outcome == 0)


def fmt(r):
    return (f"{R.iso(r['report_date'])} {r['recommendation']:7s} AFG {float(r['afg_probability']):.0%} "
            f"vs {float(r['kalshi_price']):.0%}")


def main():
    today = datetime.date.today().isoformat()
    real = sqlite3.connect(f"file:{db.DB_PATH}?mode=ro", uri=True)
    real.row_factory = sqlite3.Row
    exp = replay()

    resolved = real.execute(
        "SELECT kalshi_ticker, MIN(outcome) AS o, MAX(outcome) AS o2 FROM predictions "
        "WHERE status='Resolved' GROUP BY kalshi_ticker ORDER BY kalshi_ticker").fetchall()

    out, problems = [], []
    out.append(f"AFG RESOLVED-CONTRACT AUDIT — {today} — {len(resolved)} resolved contracts (read-only)")
    out.append("=" * 100)
    for t, o, o2 in [(r[0], r[1], r[2]) for r in resolved]:
        actual = rows_for(real, t)
        expected = rows_for(exp, t)
        allrows = rows_for(real, t, live_only=False)
        tags = []
        if o != o2:
            tags.append("RESOLVED ROWS DISAGREE ON OUTCOME")
        if not expected:
            tags.append("NOT IN PUBLISHED HISTORY")
        a_sig = [sig(r) for r in actual]
        e_sig = [sig(r) for r in expected]
        if expected and a_sig != e_sig:
            tags.append("CALLS DIFFER")
        a_closed = bool(actual) and all(r["closed"] for r in actual)
        e_closed = bool(expected) and all(r["closed"] for r in expected)
        if expected and a_closed != e_closed:
            tags.append(f"CLOSED FLAG DIFFERS (db {a_closed}, published {e_closed})")
        # scoring impact
        impact = []
        if expected and actual:
            for label, pick in (("First-Call", 0), ("Updated-Position", -1)):
                ea, aa = expected[pick], actual[pick]
                e_ok, a_ok = correct(ea["recommendation"], o), correct(aa["recommendation"], o)
                e_in = not (label == "Updated-Position" and e_closed)
                a_in = not (label == "Updated-Position" and a_closed)
                if (e_ok, e_in) != (a_ok, a_in):
                    impact.append(
                        f"{label}: scorecard shows {'excluded' if not a_in else ('CORRECT' if a_ok else 'INCORRECT')}, "
                        f"published record says {'excluded' if not e_in else ('CORRECT' if e_ok else 'INCORRECT')}")
        status = "OK" if not tags else "; ".join(tags)
        out.append("")
        out.append(f"{t}   outcome={'YES' if o == 1 else 'NO'}   [{status}]")
        out.append("    published : " + (" | ".join(fmt(r) for r in expected) or "(none)")
                   + ("   [closed]" if e_closed else ""))
        out.append("    database  : " + (" | ".join(fmt(r) for r in actual) or "(none)")
                   + ("   [closed]" if a_closed else ""))
        hidden = [r for r in allrows if r["status"] not in ("Open", "Resolved")]
        if hidden:
            out.append("    hidden    : " + " | ".join(f"id {r['id']} {r['status']} " + fmt(r) for r in hidden))
        for i in impact:
            out.append("    IMPACT    : " + i)
        if tags:
            problems.append((t, status, impact))

    out.append("")
    out.append("=" * 100)
    out.append(f"CONTRACTS NEEDING REVIEW ({len(problems)})")
    for t, s, imp in problems:
        out.append(f"  - {t}: {s}")
        for i in imp:
            out.append(f"      {i}")
    text = "\n".join(out)
    print(text)
    os.makedirs("reports", exist_ok=True)
    path = f"reports/resolved_audit_{today}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"\nSaved to {path} — attach it in chat. Nothing in the database was changed.")


if __name__ == "__main__":
    main()
