"""
05_update_scorecard.py — checks resolved markets and refreshes the scorecard.

This is a straight port of the already-tested resolve.py + scorecard.py logic
from the previous version of this project. Nothing about its behavior has
changed -- it never depended on the category/volume problem that's blocking
Phase 1, since it only ever looks up one known ticker at a time (a reliable,
already-confirmed pattern).

Run daily (this is the piece worth automating via cron/Task Scheduler first,
since it requires zero judgment calls):
    python 05_update_scorecard.py
"""

import datetime
import sys

from db import get_open_predictions_due, record_outcome, get_conn
from kalshi_client import get_market_status

SCORECARD_OUTPUT = "reports/scorecard.html"

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AFG Track Record</title>
<style>
  body {{ font-family: Georgia, 'Cambria', serif; max-width: 900px; margin: 40px auto; color: #17365D; }}
  h1 {{ border-bottom: 3px solid #17365D; padding-bottom: 8px; }}
  h2 {{ color: #365F91; border-bottom: 1px solid #4F81BD; padding-bottom: 4px; margin-top: 36px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
  th {{ background: #DCE6F1; text-align: left; padding: 8px; border: 1px solid #A6A6A6; }}
  td {{ padding: 8px; border: 1px solid #A6A6A6; }}
  .headline {{ font-size: 1.3em; font-weight: bold; }}
  .good {{ color: #1F6F3D; }}
  .bad {{ color: #A6231F; }}
  .muted {{ color: #808080; font-size: 0.9em; }}
</style>
</head>
<body>
  <h1>AFG Track Record</h1>
  <p class="muted">Generated from {n_resolved} resolved calls out of {n_total} logged.</p>
  <p class="headline">Overall Brier Score: {overall_brier} <span class="muted">(lower is better; 0 = perfect, 0.25 = coin flip)</span></p>
  <p class="headline">Kalshi Market Brier Score: {overall_kalshi_brier}</p>
  <p class="headline {edge_class}">AFG {edge_label} the market by {edge_diff} Brier points.</p>
  <h2>Win Rate by Conviction Tier</h2>
  <table>
    <tr><th>Conviction</th><th>Calls</th><th>Correct</th><th>Win Rate</th><th>Avg Brier</th></tr>
    {conviction_rows}
  </table>
  <h2>Brier Score by Category</h2>
  <table>
    <tr><th>Category</th><th>Calls Resolved</th><th>AFG Brier</th><th>Kalshi Brier</th></tr>
    {category_rows}
  </table>
  <h2>Recent Resolved Calls</h2>
  <table>
    <tr><th>Market</th><th>Category</th><th>Kalshi</th><th>AFG</th><th>Outcome</th><th>Brier (AFG / Kalshi)</th></tr>
    {recent_rows}
  </table>
</body>
</html>
"""


def _call_was_correct(r):
    if r["recommendation"] == "BUY YES":
        return r["outcome"] == 1
    if r["recommendation"] == "BUY NO":
        return r["outcome"] == 0
    return False


def check_resolutions():
    today = datetime.date.today().isoformat()
    due = get_open_predictions_due(today)

    if not due:
        print(f"[{today}] No predictions due for resolution check.")
        return

    print(f"[{today}] Checking {len(due)} predictions due for resolution...")
    resolved_count = 0
    for pred in due:
        ticker = pred.get("kalshi_ticker")
        if not ticker:
            print(f"  SKIP: '{pred['market']}' has no ticker on file.")
            continue
        try:
            status = get_market_status(ticker)
        except Exception as e:
            print(f"  ERROR checking {ticker}: {e}")
            continue
        if not status["settled"]:
            print(f"  Still open: {pred['market']} ({ticker})")
            continue
        outcome = 1 if status["result"] == "yes" else 0
        record_outcome(pred["id"], outcome)
        resolved_count += 1
        print(f"  RESOLVED: {pred['market']} -> {status['result'].upper()} "
              f"(AFG: {pred['afg_probability']:.0%}, Kalshi: {pred['kalshi_price']:.0%})")
    print(f"[{today}] Done. {resolved_count} of {len(due)} newly resolved.")


def refresh_scorecard():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"]
        resolved = [dict(r) for r in conn.execute(
            "SELECT * FROM predictions WHERE status = 'Resolved' ORDER BY contract_close_date DESC"
        ).fetchall()]

    if not resolved:
        overall_brier = overall_kalshi_brier = "n/a"
        edge_class, edge_label, edge_diff = "muted", "no data yet on", "-"
    else:
        n = len(resolved)
        overall_brier_val = sum(r["brier_score"] for r in resolved) / n
        overall_kalshi_brier_val = sum(r["kalshi_brier_score"] for r in resolved) / n
        diff = overall_kalshi_brier_val - overall_brier_val
        edge_class = "good" if diff > 0 else "bad"
        edge_label = "beat" if diff > 0 else "trailed"
        edge_diff = f"{abs(diff):.3f}"
        overall_brier = f"{overall_brier_val:.3f}"
        overall_kalshi_brier = f"{overall_kalshi_brier_val:.3f}"

    conviction_rows = []
    for tier in ["HIGH", "MEDIUM", "SPECULATIVE"]:
        subset = [r for r in resolved if r["conviction"] == tier]
        if not subset:
            conviction_rows.append(f"<tr><td>{tier}</td><td>0</td><td>-</td><td>-</td><td>-</td></tr>")
            continue
        n = len(subset)
        correct = sum(1 for r in subset if _call_was_correct(r))
        avg_brier = sum(r["brier_score"] for r in subset) / n
        conviction_rows.append(
            f"<tr><td>{tier}</td><td>{n}</td><td>{correct}</td><td>{correct/n:.0%}</td><td>{avg_brier:.3f}</td></tr>"
        )

    categories = sorted(set(r["category"] for r in resolved)) or ["Sports", "Economics", "Politics", "Crypto", "Weather"]
    category_rows = []
    for cat in categories:
        subset = [r for r in resolved if r["category"] == cat]
        if not subset:
            category_rows.append(f"<tr><td>{cat}</td><td>0</td><td>-</td><td>-</td></tr>")
            continue
        n = len(subset)
        afg_brier = sum(r["brier_score"] for r in subset) / n
        kalshi_brier = sum(r["kalshi_brier_score"] for r in subset) / n
        category_rows.append(f"<tr><td>{cat}</td><td>{n}</td><td>{afg_brier:.3f}</td><td>{kalshi_brier:.3f}</td></tr>")

    recent_rows = []
    for r in resolved[:15]:
        outcome_label = "YES" if r["outcome"] == 1 else "NO"
        recent_rows.append(
            f"<tr><td>{r['market']}</td><td>{r['category']}</td><td>{r['kalshi_price']:.0%}</td>"
            f"<td>{r['afg_probability']:.0%}</td><td>{outcome_label}</td>"
            f"<td>{r['brier_score']:.3f} / {r['kalshi_brier_score']:.3f}</td></tr>"
        )

    html = HTML_TEMPLATE.format(
        n_resolved=len(resolved), n_total=total,
        overall_brier=overall_brier, overall_kalshi_brier=overall_kalshi_brier,
        edge_class=edge_class, edge_label=edge_label, edge_diff=edge_diff,
        conviction_rows="\n    ".join(conviction_rows),
        category_rows="\n    ".join(category_rows),
        recent_rows="\n    ".join(recent_rows) if recent_rows else "<tr><td colspan='6'>No resolved calls yet.</td></tr>",
    )

    with open(SCORECARD_OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Scorecard written to {SCORECARD_OUTPUT} ({len(resolved)} resolved calls)")


if __name__ == "__main__":
    try:
        check_resolutions()
        refresh_scorecard()
    except Exception as e:
        print(f"05_update_scorecard.py failed: {e}", file=sys.stderr)
        sys.exit(1)
