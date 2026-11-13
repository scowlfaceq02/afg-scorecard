"""
06_build_scorecard.py  —  AFG Scorecard Builder
(November 11th, 2026: refuses to build unless check_settlements.py passes.)
Final-Call Only Scoring  ·  Effective November 6th, 2026

SCORING RULE:
  Only the most recently published BUY YES or BUY NO call per ticker,
  at or before the settlement date, is scored.
  Direction changes carry no penalty — Bayesian updating is correct behavior.
  Positions closed to NO TRADE before settlement are excluded from the
  win/loss record and appear in the Closed Positions disclosure table only.

CHANGES FROM PRIOR VERSION:
  - First-Call scoring loop removed entirely.
  - "Position Changes" section removed from HTML output.
  - Deduplication now reads LAST call per ticker (not first).
  - Single accuracy track: Final-Call.
"""

import sqlite3
import os
import sys
import shutil
from datetime import date, datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB_PATH          = "afg_scorecard.db"
SCORECARD_DIR    = os.path.join("reports", "scorecards")
DOCS_DIR         = "docs"
TODAY            = date.today().isoformat()

# ── DB HELPERS ────────────────────────────────────────────────────────────────

def get_connection():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found. Run from C:\\Users\\qwhit\\AFG\\")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def _parse_date(val):
    """Return a date object from ISO string, MM/DD/YYYY, or M/D/YYYY. Never compare raw strings."""
    if val is None:
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


# ── FETCH FINAL CALLS ─────────────────────────────────────────────────────────

def fetch_scored_positions(conn):
    """
    For every resolved ticker, return the LAST published BUY YES / BUY NO call
    whose published_date <= settlement_date.

    Returns list of dicts with keys:
      ticker, market, category, final_call, afg_pct, kalshi_pct,
      published_date, settled_date, outcome, brier, closed
    """
    cur = conn.cursor()

    # Pull all resolved contracts
    cur.execute("""
        SELECT DISTINCT ticker
        FROM predictions
        WHERE outcome IS NOT NULL AND outcome != ''
        AND status NOT IN ('Void', 'Superseded')
    """)
    resolved_tickers = [r[0] for r in cur.fetchall()]

    scored = []
    closed = []

    for ticker in resolved_tickers:
        # Get settlement info
        cur.execute("""
            SELECT outcome, close_date, market, category, resolution_date
            FROM predictions
            WHERE ticker = ? AND outcome IS NOT NULL AND outcome != ''
            AND status NOT IN ('Void', 'Superseded')
            ORDER BY rowid DESC LIMIT 1
        """, (ticker,))
        row = cur.fetchone()
        if not row:
            continue
        outcome, close_date_raw, market, category, resolution_date_raw = row
        settle_date = _parse_date(close_date_raw)

        # Get ALL published calls for this ticker, in date order
        cur.execute("""
            SELECT recommendation, afg_probability, kalshi_price, published_date
            FROM predictions
            WHERE ticker = ?
            AND recommendation IN ('BUY YES', 'BUY NO', 'NO TRADE')
            AND status NOT IN ('Void', 'Superseded')
            ORDER BY published_date ASC, rowid ASC
        """, (ticker,))
        calls = cur.fetchall()

        if not calls:
            continue

        # Find the last published call at or before settlement
        last_call = None
        for rec, afg_p, kal_p, pub_date_raw in calls:
            pub_date = _parse_date(pub_date_raw)
            if settle_date and pub_date and pub_date > settle_date:
                break
            last_call = (rec, afg_p, kal_p, pub_date_raw)

        if last_call is None:
            continue

        final_rec, afg_p, kal_p, pub_date = last_call

        # Convert probabilities (stored as 0.0–1.0 decimals or 0–100 ints)
        try:
            afg_pct    = float(afg_p) * 100 if float(afg_p) <= 1.0 else float(afg_p)
            kalshi_pct = float(kal_p) * 100 if float(kal_p) <= 1.0 else float(kal_p)
        except (TypeError, ValueError):
            afg_pct = kalshi_pct = 0.0

        # Closed = last call was NO TRADE
        is_closed = (final_rec == "NO TRADE")

        # Brier score (on AFG probability at final call)
        # outcome stored as integer 0/1 — also accept legacy "YES"/"NO" strings
        _out_str = str(outcome).strip().upper()
        o = 1 if (_out_str == "1" or _out_str == "YES") else 0
        p = afg_pct / 100.0
        brier = round((p - o) ** 2, 3)

        entry = {
            "ticker":          ticker,
            "market":          market or ticker,
            "category":        category or "—",
            "final_call":      final_rec,
            "afg_pct":         round(afg_pct, 1),
            "kalshi_pct":      round(kalshi_pct, 1),
            "published_date":  pub_date,
            "settle_date":     close_date_raw,
            "resolution_date": resolution_date_raw,
            "outcome":         str(outcome).upper(),
            "brier":           brier,
            "closed":          is_closed,
        }

        if is_closed:
            # Compute "would have been" for disclosure table
            if final_rec == "BUY YES":
                entry["would_have"] = "✓ Correct" if o == 1 else "✗ Incorrect"
            else:
                entry["would_have"] = "✓ Correct" if o == 0 else "✗ Incorrect"
            closed.append(entry)
        else:
            # Score it
            if final_rec == "BUY YES":
                entry["result"] = "Correct" if o == 1 else "Incorrect"
            else:
                entry["result"] = "Correct" if o == 0 else "Incorrect"
            scored.append(entry)

    return scored, closed


# ── SUMMARY STATS ─────────────────────────────────────────────────────────────

def compute_stats(scored):
    n = len(scored)
    if n == 0:
        return {"n": 0, "correct": 0, "incorrect": 0, "accuracy": 0.0,
                "afg_brier": 0.0, "mkt_brier": 0.0}
    correct   = sum(1 for r in scored if r["result"] == "Correct")
    incorrect = n - correct
    afg_brier = sum(r["brier"] for r in scored) / n

    # Market Brier (Kalshi price at time of final call)
    mkt_briers = []
    for r in scored:
        p = r["kalshi_pct"] / 100.0
        o = 1 if r["outcome"] == "YES" else 0
        mkt_briers.append((p - o) ** 2)
    mkt_brier = sum(mkt_briers) / n if mkt_briers else 0.0

    # Category breakdown
    cats = {}
    for r in scored:
        c = r["category"]
        if c not in cats:
            cats[c] = {"correct": 0, "total": 0}
        cats[c]["total"] += 1
        if r["result"] == "Correct":
            cats[c]["correct"] += 1

    return {
        "n":          n,
        "correct":    correct,
        "incorrect":  incorrect,
        "accuracy":   round(correct / n * 100, 1),
        "afg_brier":  round(afg_brier, 3),
        "mkt_brier":  round(mkt_brier, 3),
        "categories": cats,
    }


# ── HTML BUILDER ──────────────────────────────────────────────────────────────

STYLES = """
<style>
:root{--navy:#0D1B2A;--gold:#C9A84C;--white:#FFFFFF;--light:#F5F5F0;
--mid:#E8E8E2;--gray:#CCCCCC;--green:#1A7A4A;--red:#B22222;--text:#1A1A1A;--muted:#555}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Georgia,serif;background:var(--light);color:var(--text);line-height:1.6}
header{background:var(--navy);padding:36px 24px 28px;text-align:center}
header .eyebrow{font-family:Arial,sans-serif;font-size:11px;letter-spacing:2.5px;text-transform:uppercase;color:var(--gold);margin-bottom:8px}
header h1{font-size:26px;font-weight:bold;color:var(--white);margin-bottom:6px}
header .subtitle{font-size:13px;color:var(--gray);font-style:italic}
header .updated{margin-top:10px;font-family:Arial,sans-serif;font-size:11px;color:var(--gold);letter-spacing:1px}
main{max-width:960px;margin:0 auto;padding:32px 20px 60px}
.methodology-banner{background:var(--navy);color:var(--gold);border-left:4px solid var(--gold);padding:14px 18px;border-radius:4px;margin-bottom:28px;font-family:Arial,sans-serif;font-size:13px;line-height:1.6}
.methodology-banner strong{color:var(--white)}
.section-title{font-family:Arial,sans-serif;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--gold);background:var(--navy);padding:8px 14px;border-radius:3px 3px 0 0}
.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;background:var(--gray);border:1px solid var(--gray);border-radius:0 0 4px 4px;margin-bottom:32px;overflow:hidden}
.stat-cell{background:var(--white);padding:18px 14px;text-align:center}
.stat-cell .stat-label{font-family:Arial,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.stat-cell .stat-value{font-size:24px;font-weight:bold;color:var(--navy);line-height:1.1}
.stat-cell .stat-sub{font-size:11px;color:var(--muted);margin-top:3px}
.stat-cell.highlight .stat-value{color:var(--green)}
.brier-row{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--gray);border:1px solid var(--gray);border-radius:0 0 4px 4px;margin-bottom:32px;overflow:hidden}
.brier-cell{background:var(--white);padding:16px 18px;text-align:center}
.brier-cell .label{font-family:Arial,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
.brier-cell .value{font-size:22px;font-weight:bold}
.brier-cell.afg .value{color:var(--red)}
.brier-cell.mkt .value{color:var(--green)}
.brier-cell .note{font-size:11px;color:var(--muted);margin-top:4px;font-style:italic}
.cat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;background:var(--gray);border:1px solid var(--gray);border-radius:0 0 4px 4px;margin-bottom:32px;overflow:hidden}
.cat-cell{background:var(--white);padding:16px 12px;text-align:center}
.cat-cell .cat-name{font-family:Arial,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.cat-cell .cat-acc{font-size:20px;font-weight:bold;color:var(--navy)}
.cat-cell .cat-rec{font-size:11px;color:var(--muted);margin-top:2px}
.table-wrap{margin-bottom:36px;border-radius:0 0 4px 4px;overflow:hidden;border:1px solid var(--gray)}
table{width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:12px}
thead th{background:var(--navy);color:var(--white);padding:9px 10px;text-align:center;font-weight:bold;font-size:11px;letter-spacing:.5px}
thead th:first-child{text-align:left}
tbody tr:nth-child(even){background:var(--mid)}
tbody tr:nth-child(odd){background:var(--white)}
tbody td{padding:8px 10px;border-bottom:1px solid var(--gray);vertical-align:middle;text-align:center}
tbody td:first-child{font-weight:bold;color:var(--navy)}
tbody td:first-child,tbody td:nth-child(2){text-align:left}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:bold;letter-spacing:.5px}
.correct{background:var(--green);color:var(--white)}
.incorrect{background:var(--red);color:var(--white)}
.buy-yes{background:#1A5276;color:var(--white)}
.buy-no{background:#6E2F1A;color:var(--white)}
.closed-note{background:var(--mid);border-left:3px solid var(--navy);padding:10px 14px;font-family:Arial,sans-serif;font-size:12px;color:var(--muted)}
.legend-box{background:var(--white);border:1px solid var(--gray);border-radius:4px;padding:18px 20px;margin-bottom:32px;font-family:Arial,sans-serif;font-size:12px;color:var(--muted)}
.legend-box h3{font-size:12px;font-weight:bold;color:var(--navy);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px}
footer{background:var(--navy);color:var(--gray);text-align:center;padding:24px 20px;font-family:Arial,sans-serif;font-size:11px;line-height:1.8}
footer a{color:var(--gold);text-decoration:none}
</style>
"""


def badge(label, css_class):
    return f'<span class="badge {css_class}">{label}</span>'


def build_html(scored, closed, stats, today_str):
    cats = stats.get("categories", {})

    # Category grid cells
    cat_cells = ""
    for cat in ["Sports", "Economics", "Politics", "Culture", "Weather"]:
        d = cats.get(cat, {"correct": 0, "total": 0})
        t = d["total"]
        c = d["correct"]
        acc = f"{round(c/t*100)}%" if t else "—"
        rec = f"{c} of {t} scored" if t else "No data yet"
        cat_cells += f"""
        <div class="cat-cell">
          <div class="cat-name">{cat}</div>
          <div class="cat-acc">{acc}</div>
          <div class="cat-rec">{rec}</div>
        </div>"""

    # Resolved forecasts rows
    forecast_rows = ""
    for i, r in enumerate(sorted(scored, key=lambda x: x.get("settle_date", "")), 1):
        call_badge  = badge("BUY YES", "buy-yes") if r["final_call"] == "BUY YES" else badge("BUY NO", "buy-no")
        result_badge = badge("✓ Correct", "correct") if r["result"] == "Correct" else badge("✗ Incorrect", "incorrect")
        forecast_rows += f"""
        <tr>
          <td>{i}</td>
          <td>{r['market']}</td>
          <td>{r['category']}</td>
          <td>{call_badge}</td>
          <td>{r['afg_pct']:.0f}%</td>
          <td>{r['kalshi_pct']:.0f}%</td>
          <td>{r['outcome']}</td>
          <td>{result_badge}</td>
          <td>{r['brier']:.3f}</td>
        </tr>"""

    # Closed positions rows
    closed_rows = ""
    for i, r in enumerate(closed, 1):
        call_badge = badge("BUY YES", "buy-yes") if r["final_call"] == "BUY YES" else badge("BUY NO", "buy-no")
        wh = r.get("would_have", "—")
        wh_badge = badge("✓ Correct", "correct") if "Correct" in wh else badge("✗ Incorrect", "incorrect")
        # Parse close date for display
        cd = _parse_date(r.get("settle_date")) or r.get("settle_date", "—")
        closed_rows += f"""
        <tr>
          <td>{i}</td>
          <td>{r['market']}</td>
          <td>{r['category']}</td>
          <td>{call_badge}</td>
          <td>{r['afg_pct']:.0f}%</td>
          <td>{cd}</td>
          <td>{r['outcome']}</td>
          <td>{wh_badge}</td>
        </tr>"""

    brier_gap   = round(stats["afg_brier"] - stats["mkt_brier"], 3)
    brier_color = "var(--red)" if brier_gap > 0 else "var(--green)"
    brier_note  = f"AFG trails market by {brier_gap:.3f} points" if brier_gap > 0 else f"AFG leads market by {abs(brier_gap):.3f} points"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AFG Forecast Accuracy Index — Axiom Forecasting Group</title>
  {STYLES}
</head>
<body>
<header>
  <div class="eyebrow">Axiom Forecasting Group</div>
  <h1>AFG Forecast Accuracy Index</h1>
  <div class="subtitle">Kalshi prediction market research · Sports · Economics · Politics · Culture · Weather</div>
  <div class="updated">Last updated: {today_str}</div>
</header>
<main>
  <div class="methodology-banner">
    AFG is scored on the <strong>final published call</strong> at the time of contract settlement,
    following Good Judgment and Superforecaster methodology.
  </div>

  <div class="section-title">Final-Call Accuracy — Summary</div>
  <div class="summary-grid">
    <div class="stat-cell highlight">
      <div class="stat-label">Final-Call Accuracy</div>
      <div class="stat-value">{stats['accuracy']}%</div>
      <div class="stat-sub">{stats['correct']} correct of {stats['n']} scored</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Total Settled</div>
      <div class="stat-value">{stats['n'] + len(closed)}</div>
      <div class="stat-sub">contracts resolved</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Scored</div>
      <div class="stat-value">{stats['n']}</div>
      <div class="stat-sub">live call at settlement</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Correct</div>
      <div class="stat-value">{stats['correct']}</div>
      <div class="stat-sub">final call matched outcome</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Incorrect</div>
      <div class="stat-value">{stats['incorrect']}</div>
      <div class="stat-sub">final call missed</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Excluded</div>
      <div class="stat-value">{len(closed)}</div>
      <div class="stat-sub">closed before settlement</div>
    </div>
  </div>

  <div class="section-title">Calibration — Brier Score Comparison</div>
  <div class="brier-row">
    <div class="brier-cell afg">
      <div class="label">AFG Brier Score</div>
      <div class="value">{stats['afg_brier']:.3f}</div>
      <div class="note">Lower is better · Final call probabilities</div>
    </div>
    <div class="brier-cell mkt">
      <div class="label">Market (Kalshi) Brier Score</div>
      <div class="value">{stats['mkt_brier']:.3f}</div>
      <div class="note">Market price at time of final call</div>
    </div>
  </div>

  <div class="section-title">Final-Call Accuracy by Category</div>
  <div class="cat-grid">{cat_cells}
  </div>

  <div class="section-title">All Resolved Forecasts</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th><th>Contract</th><th>Category</th><th>Final Call</th>
          <th>AFG %</th><th>Market %</th><th>Settled</th><th>Result</th><th>Brier</th>
        </tr>
      </thead>
      <tbody>{forecast_rows}
      </tbody>
    </table>
  </div>

  <div class="section-title">Closed Positions — Disclosure Table</div>
  <div class="closed-note">
    These positions were exited (NO TRADE) before contract settlement.
    They are excluded from the win/loss record.
    "Would Have Been" shows the hypothetical result had the position been held to settlement.
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th><th>Contract</th><th>Category</th><th>Last Call</th>
          <th>AFG %</th><th>Closed</th><th>Settled</th><th>Would Have Been</th>
        </tr>
      </thead>
      <tbody>{closed_rows}
      </tbody>
    </table>
  </div>

  <div class="legend-box">
    <h3>What is a Brier Score?</h3>
    <p>A Brier score measures probability calibration. It is calculated as (AFG probability − actual outcome)².
    <strong>Lower is better.</strong> A perfect score is 0.000. Random guessing scores 0.250.
    AFG's goal is to score lower than the Kalshi market price on every resolved contract.</p>
    <br/>
    <p><strong>AFG Brier: {stats['afg_brier']:.3f}</strong> &nbsp;·&nbsp;
    <strong>Market Brier: {stats['mkt_brier']:.3f}</strong> &nbsp;·&nbsp;
    <span style="color:{brier_color}">{brier_note}</span> across {stats['n']} scored positions.</p>
  </div>

  <div class="legend-box">
    <h3>Publishing Cadence &amp; Methodology</h3>
    <p>AFG publishes research every <strong>Monday, Wednesday, and Friday</strong>.
    Probabilities are derived using Bayesian reasoning, historical base rates, and
    behavioral finance principles.</p>
    <br/>
    <p>Scoring uses <strong>final-call accuracy only</strong> — the most recently published
    recommendation at the time of contract settlement. All position changes are logged internally
    for calibration analysis.
    Subscribe at <a href="https://axiomforecastinggroup.substack.com/welcome" target="_blank">axiomforecastinggroup.substack.com</a>.</p>
  </div>
</main>
<footer>
  <p><strong style="color:var(--gold)">Axiom Forecasting Group</strong></p>
  <p style="margin-top:6px">
    <a href="https://axiomforecastinggroup.substack.com/welcome" target="_blank">Substack</a>
    &nbsp;·&nbsp;
    <a href="https://scowlfaceq02.github.io/afg-scorecard/" target="_blank">Scorecard</a>
  </p>
  <p style="margin-top:10px;font-size:10px;color:#888">
    For informational purposes only. Not financial or investment advice.
    All forecasts are probabilistic estimates subject to revision as new information becomes available.
  </p>
</footer>
</body>
</html>"""


# ── WORD SCORECARD ────────────────────────────────────────────────────────────

def build_word_scorecard(scored, closed, stats, today_str, out_path):
    """Build a Word .docx scorecard with final-call only scoring."""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        import docx.oxml as oxml
    except ImportError:
        print("python-docx not installed — skipping Word scorecard. Run: pip install python-docx")
        return

    doc = Document()

    # Narrow margins
    for section in doc.sections:
        section.top_margin    = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin   = Inches(0.9)
        section.right_margin  = Inches(0.9)

    NAVY  = RGBColor(0x0D, 0x1B, 0x2A)
    GOLD  = RGBColor(0xC9, 0xA8, 0x4C)
    GREEN = RGBColor(0x1A, 0x7A, 0x4A)
    RED   = RGBColor(0xB2, 0x22, 0x22)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)

    def set_cell_bg(cell, hex_color):
        tc   = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd  = oxml.OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)

    # Title
    title = doc.add_heading("AFG FORECAST ACCURACY INDEX", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = NAVY
        run.font.size = Pt(16)

    sub = doc.add_paragraph(f"Axiom Forecasting Group  ·  Final-Call Only Scoring  ·  {today_str}")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].font.size = Pt(10)
    sub.runs[0].font.color.rgb = GOLD

    doc.add_paragraph()

    # Summary stats
    summ = doc.add_paragraph()
    summ.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = summ.add_run(
        f"Scored: {stats['n']}    Correct: {stats['correct']}    "
        f"Incorrect: {stats['incorrect']}    Accuracy: {stats['accuracy']}%    "
        f"AFG Brier: {stats['afg_brier']:.3f}    Market Brier: {stats['mkt_brier']:.3f}    "
        f"Excluded (Closed): {len(closed)}"
    )
    r.font.bold = True
    r.font.size = Pt(10)

    doc.add_paragraph()

    # Resolved forecasts table
    hdr = doc.add_heading("All Resolved Forecasts — Final-Call Only", level=2)
    hdr.runs[0].font.color.rgb = NAVY

    t = doc.add_table(rows=1, cols=8)
    t.style = "Table Grid"
    hdrs = ["#", "Contract", "Category", "Final Call", "AFG %", "Market %", "Settled", "Result"]
    for i, h in enumerate(hdrs):
        cell = t.rows[0].cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].font.bold  = True
        cell.paragraphs[0].runs[0].font.color.rgb = WHITE
        cell.paragraphs[0].runs[0].font.size  = Pt(9)
        set_cell_bg(cell, "0D1B2A")

    for idx, r in enumerate(sorted(scored, key=lambda x: x.get("settle_date", "")), 1):
        row = t.add_row()
        vals = [
            str(idx), r["market"], r["category"], r["final_call"],
            f"{r['afg_pct']:.0f}%", f"{r['kalshi_pct']:.0f}%",
            r["outcome"],
            "✓ Correct" if r["result"] == "Correct" else "✗ Incorrect"
        ]
        for i, v in enumerate(vals):
            cell = row.cells[i]
            cell.text = v
            run = cell.paragraphs[0].runs[0]
            run.font.size = Pt(9)
            if i == 7:
                run.font.bold = True
                run.font.color.rgb = GREEN if r["result"] == "Correct" else RED

    doc.add_paragraph()

    # Closed positions table
    hdr2 = doc.add_heading("Closed Positions — Disclosure Table", level=2)
    hdr2.runs[0].font.color.rgb = NAVY

    note = doc.add_paragraph(
        "Excluded from win/loss record. 'Would Have Been' shows hypothetical result had position been held to settlement."
    )
    note.runs[0].font.size = Pt(9)
    note.runs[0].font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    t2 = doc.add_table(rows=1, cols=7)
    t2.style = "Table Grid"
    hdrs2 = ["#", "Contract", "Category", "Last Call", "AFG %", "Settled", "Would Have Been"]
    for i, h in enumerate(hdrs2):
        cell = t2.rows[0].cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.color.rgb = WHITE
        cell.paragraphs[0].runs[0].font.size = Pt(9)
        set_cell_bg(cell, "444444")

    for idx, r in enumerate(closed, 1):
        row = t2.add_row()
        wh = r.get("would_have", "—")
        vals = [
            str(idx), r["market"], r["category"], r["final_call"],
            f"{r['afg_pct']:.0f}%", r["outcome"], wh
        ]
        for i, v in enumerate(vals):
            cell = row.cells[i]
            cell.text = v
            run = cell.paragraphs[0].runs[0]
            run.font.size = Pt(9)
            if i == 6:
                run.font.bold = True
                run.font.color.rgb = GREEN if "Correct" in wh else RED

    doc.save(out_path)
    print(f"Word scorecard saved: {out_path}")


# ── RESOLUTION SOCIAL POST ────────────────────────────────────────────────────

def build_resolution_post(newly_resolved, today_str, out_dir):
    """Write a Twitter/X resolution post for any newly settled contracts."""
    if not newly_resolved:
        return
    lines = [f"AFG Resolution Update — {today_str}", ""]
    for r in newly_resolved:
        result = r.get("result", "")
        emoji  = "✅" if result == "Correct" else "❌"
        lines.append(
            f"{emoji} {r['market']} settled {r['outcome']}. "
            f"AFG final call: {r['final_call']} @ {r['afg_pct']:.0f}%. "
            f"{'Correct.' if result == 'Correct' else 'Incorrect.'}"
        )
    lines += ["", "Track record → https://scowlfaceq02.github.io/afg-scorecard/"]
    out = os.path.join(out_dir, f"AFG_Resolution_Post_{today_str}.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Resolution post: {out}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(SCORECARD_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR,      exist_ok=True)

    # Settlement cross-check (added November 11th, 2026). Nothing is built
    # unless every resolved outcome matches Kalshi's settlement record or a
    # documented early resolution. There is no bypass.
    from check_settlements import check_settlements
    print("Checking stored outcomes against Kalshi's settlement records...")
    _rep, _probs = check_settlements(DB_PATH, verbose=True)
    if _probs:
        print("\nSTOP: scorecard not built. Fix the problems above and re-run.")
        sys.exit(1)

    conn = get_connection()
    scored, closed = fetch_scored_positions(conn)
    conn.close()

    stats    = compute_stats(scored)
    today_str = datetime.now().strftime("%B %d, %Y")

    print(f"\n{'='*60}")
    print(f"AFG SCORECARD — FINAL-CALL ONLY — {today_str}")
    print(f"{'='*60}")
    print(f"Scored positions : {stats['n']}")
    print(f"Correct          : {stats['correct']}")
    print(f"Incorrect        : {stats['incorrect']}")
    print(f"Accuracy         : {stats['accuracy']}%")
    print(f"AFG Brier        : {stats['afg_brier']:.3f}")
    print(f"Market Brier     : {stats['mkt_brier']:.3f}")
    print(f"Excluded (closed): {len(closed)}")

    # Premature resolution guard
    # Allow early resolution when resolution_date is set and in the past
    # (contract settled before its official close date — e.g. official departed early)
    today_date = date.today()
    for r in scored:
        settle = _parse_date(r.get("settle_date"))
        if settle and settle > today_date:
            res_date = _parse_date(r.get("resolution_date"))
            if res_date is None or res_date > today_date:
                print(f"\nSTOP: {r['ticker']} shows as Resolved but close date {settle} is in the future.")
                print("Run the premature-resolution fix before proceeding.")
                sys.exit(1)

    # Build HTML
    html = build_html(scored, closed, stats, today_str)
    html_path = os.path.join(DOCS_DIR, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML scorecard  : {html_path}")

    # Build Word scorecard
    word_path = os.path.join(SCORECARD_DIR, f"AFG_Scorecard_{TODAY}.docx")
    build_word_scorecard(scored, closed, stats, today_str, word_path)

    # Resolution post (all newly resolved since last run — caller filters if needed)
    build_resolution_post(scored[-3:] if scored else [], TODAY, SCORECARD_DIR)

    print(f"\nDone. Git push to publish: git add -A && git commit -m \"scorecard {TODAY}\" && git push")


if __name__ == "__main__":
    main()
