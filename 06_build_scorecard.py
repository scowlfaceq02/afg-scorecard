"""
06_build_scorecard.py — AFG's elite performance scorecard.

Reads every RESOLVED prediction from the scorecard database and produces:
  1. reports/AFG_Scorecard_<date>.docx   — polished Word doc for your records
  2. docs/index.html                      — GitHub Pages website (auto-hosts)

Metrics:
  - Overall Brier score (AFG vs. Kalshi market) + skill delta
  - Brier score by category (Sports, Economics, Politics, Culture, Weather)
  - Win rate overall and by conviction tier
  - Calibration summary and recent resolved calls

Lower Brier = better. 0 = perfect, 0.25 = coin flip, 1.0 = perfectly wrong.

Run:
    python 06_build_scorecard.py
"""

import os
from datetime import date

import pandas as pd
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from db import get_conn

NAVY = RGBColor(0x17, 0x36, 0x5D)
BLUE = RGBColor(0x36, 0x5F, 0x91)
GREEN = RGBColor(0x1F, 0x6F, 0x3D)
RED = RGBColor(0xA6, 0x23, 0x1F)
GRAY = RGBColor(0x80, 0x80, 0x80)
HEADER_FILL = "DCE6F1"
BORDER_COLOR = "A6A6A6"
FONT = "Cambria"

CATEGORY_ORDER = ["Sports", "Economics", "Politics", "Culture", "Weather"]

DOCX_DIR = "reports"
WEB_DIR = "docs"   # GitHub Pages serves from /docs


# ---------------------------------------------------------------- data

def load_resolved():
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM predictions WHERE status = 'Resolved' ORDER BY contract_close_date DESC"
        ).fetchall()]
    return rows


def call_correct(r):
    if r["recommendation"] == "BUY YES":
        return r["outcome"] == 1
    if r["recommendation"] == "BUY NO":
        return r["outcome"] == 0
    return None


def compute_metrics(resolved):
    n = len(resolved)
    if n == 0:
        return None

    afg_brier = sum(r["brier_score"] for r in resolved) / n
    kalshi_brier = sum(r["kalshi_brier_score"] for r in resolved) / n
    correct = [call_correct(r) for r in resolved if call_correct(r) is not None]
    win_rate = sum(correct) / len(correct) if correct else 0.0

    by_cat = {}
    for cat in CATEGORY_ORDER:
        subset = [r for r in resolved if r["category"] == cat]
        if subset:
            c = [call_correct(x) for x in subset if call_correct(x) is not None]
            by_cat[cat] = {
                "n": len(subset),
                "afg_brier": sum(x["brier_score"] for x in subset) / len(subset),
                "kalshi_brier": sum(x["kalshi_brier_score"] for x in subset) / len(subset),
                "win_rate": (sum(c) / len(c)) if c else None,
            }

    by_conv = {}
    for tier in ["HIGH", "MEDIUM", "SPECULATIVE"]:
        subset = [r for r in resolved if str(r["conviction"]).upper() == tier]
        if subset:
            c = [call_correct(x) for x in subset if call_correct(x) is not None]
            by_conv[tier] = {
                "n": len(subset),
                "win_rate": (sum(c) / len(c)) if c else None,
                "afg_brier": sum(x["brier_score"] for x in subset) / len(subset),
            }

    return {
        "n": n, "afg_brier": afg_brier, "kalshi_brier": kalshi_brier,
        "skill_delta": kalshi_brier - afg_brier, "win_rate": win_rate,
        "by_cat": by_cat, "by_conv": by_conv,
    }


# ---------------------------------------------------------------- docx

def _run(p, text, size=10.5, bold=False, italic=False, color=None, underline=False):
    r = p.add_run(text)
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.underline = underline
    if color:
        r.font.color.rgb = color
    return r


def _shade(cell, hexcolor):
    sh = OxmlElement("w:shd")
    sh.set(qn("w:fill"), hexcolor)
    cell._tc.get_or_add_tcPr().append(sh)


def _borders(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "2"); e.set(qn("w:color"), BORDER_COLOR)
        b.append(e)
    tcPr.append(b)


def _heading(doc, text):
    p = doc.add_paragraph()
    _run(p, text, size=14, bold=True, color=BLUE, underline=True)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)


def _table(doc, headers, rows, widths, colorers=None):
    t = doc.add_table(rows=1, cols=len(headers))
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]; c.text = ""
        _run(c.paragraphs[0], h, size=9.5, bold=True, color=NAVY)
        _shade(c, HEADER_FILL); _borders(c)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            c = cells[i]; c.text = ""
            color = colorers[i](val) if colorers and colorers[i] else None
            _run(c.paragraphs[0], str(val), size=9.5, bold=(color is not None), color=color)
            _borders(c)
    # explicit widths (fit page)
    tblPr = t._tbl.tblPr
    for old in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old)
    tblW = OxmlElement("w:tblW"); tblW.set(qn("w:w"), str(sum(widths))); tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)
    grid = t._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        t._tbl.remove(grid)
    grid = OxmlElement("w:tblGrid")
    for w in widths:
        gc = OxmlElement("w:gridCol"); gc.set(qn("w:w"), str(w)); grid.append(gc)
    t._tbl.insert(list(t._tbl).index(tblPr) + 1, grid)
    for r in t.rows:
        for i, c in enumerate(r.cells):
            if i < len(widths):
                tcPr = c._tc.get_or_add_tcPr()
                for old in tcPr.findall(qn("w:tcW")):
                    tcPr.remove(old)
                w = OxmlElement("w:tcW"); w.set(qn("w:w"), str(widths[i])); w.set(qn("w:type"), "dxa")
                tcPr.append(w)
    return t


def build_docx(resolved, m, out_path):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for s in ("left", "right", "top", "bottom"):
        setattr(sec, f"{s}_margin", Inches(0.5))
    doc.styles["Normal"].font.name = FONT
    doc.styles["Normal"].font.size = Pt(10.5)

    # Title
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, "Axiom Forecasting Group", size=22, bold=True, color=NAVY)
    pbdr = OxmlElement("w:pBdr"); bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "12"); bottom.set(qn("w:space"), "4"); bottom.set(qn("w:color"), "17365D")
    pbdr.append(bottom); p._p.get_or_add_pPr().append(pbdr)
    p2 = doc.add_paragraph(); p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p2, "Performance Scorecard", size=12, bold=True, color=NAVY)
    _run(p2, f"   |   {date.today().strftime('%B %d, %Y')}   |   Track Record", size=11, color=BLUE)
    p2.paragraph_format.space_after = Pt(10)

    if m is None:
        _run(doc.add_paragraph(), "No resolved predictions yet. The scorecard populates as markets settle.", italic=True)
        doc.save(out_path); return

    # Headline metrics
    _heading(doc, "Headline Performance")
    beat = m["skill_delta"] > 0
    hp = doc.add_paragraph()
    _run(hp, f"AFG Brier Score: {m['afg_brier']:.3f}", size=12, bold=True, color=NAVY)
    _run(hp, f"    vs. Kalshi Market: {m['kalshi_brier']:.3f}", size=12, color=GRAY)
    hp.paragraph_format.space_after = Pt(2)
    dp = doc.add_paragraph()
    _run(dp, f"AFG {'beats' if beat else 'trails'} the market by {abs(m['skill_delta']):.3f} Brier points",
         size=11, bold=True, color=(GREEN if beat else RED))
    _run(dp, f"  across {m['n']} resolved calls  •  Win rate: {m['win_rate']:.0%}", size=11, color=GRAY)

    # Category table
    _heading(doc, "Brier Score by Category")
    cat_rows = []
    for cat in CATEGORY_ORDER:
        d = m["by_cat"].get(cat)
        if d:
            wr = f"{d['win_rate']:.0%}" if d["win_rate"] is not None else "—"
            cat_rows.append([cat, d["n"], f"{d['afg_brier']:.3f}", f"{d['kalshi_brier']:.3f}", wr])
        else:
            cat_rows.append([cat, 0, "—", "—", "—"])
    _table(doc, ["Category", "Resolved", "AFG Brier", "Kalshi Brier", "Win Rate"],
           cat_rows, [3200, 1900, 1900, 1900, 1900])

    # Conviction table
    _heading(doc, "Performance by Conviction Tier")
    conv_rows = []
    for tier in ["HIGH", "MEDIUM", "SPECULATIVE"]:
        d = m["by_conv"].get(tier)
        if d:
            wr = f"{d['win_rate']:.0%}" if d["win_rate"] is not None else "—"
            conv_rows.append([tier, d["n"], wr, f"{d['afg_brier']:.3f}"])
        else:
            conv_rows.append([tier, 0, "—", "—"])
    _table(doc, ["Conviction", "Resolved", "Win Rate", "AFG Brier"],
           conv_rows, [3000, 2600, 2600, 2600])

    # Recent resolved
    _heading(doc, "Recent Resolved Calls")
    def rec_color(v): return GREEN if v == "YES" else RED
    recent = []
    for r in resolved[:15]:
        recent.append([
            r["market"][:45], r["category"],
            f"{r['kalshi_price']:.0%}", f"{r['afg_probability']:.0%}",
            "YES" if r["outcome"] == 1 else "NO",
            "✓" if call_correct(r) else "✗",
        ])
    _table(doc, ["Market", "Category", "Kalshi", "AFG", "Outcome", "Hit"],
           recent, [4200, 1500, 1100, 1100, 1400, 1500],
           colorers=[None, None, None, None, rec_color, None])

    doc.save(out_path)


# ---------------------------------------------------------------- website

def build_website(resolved, m, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    updated = date.today().strftime("%B %d, %Y")

    if m is None:
        body = "<p class='muted'>No resolved predictions yet. The scorecard populates as markets settle.</p>"
    else:
        beat = m["skill_delta"] > 0
        delta_class = "good" if beat else "bad"
        delta_word = "beats" if beat else "trails"

        cat_rows = ""
        for cat in CATEGORY_ORDER:
            d = m["by_cat"].get(cat)
            if d:
                wr = f"{d['win_rate']:.0%}" if d["win_rate"] is not None else "—"
                cat_beat = "good" if d["kalshi_brier"] > d["afg_brier"] else "bad"
                cat_rows += (f"<tr><td>{cat}</td><td>{d['n']}</td>"
                             f"<td class='{cat_beat}'>{d['afg_brier']:.3f}</td>"
                             f"<td>{d['kalshi_brier']:.3f}</td><td>{wr}</td></tr>")
            else:
                cat_rows += f"<tr><td>{cat}</td><td>0</td><td>—</td><td>—</td><td>—</td></tr>"

        conv_rows = ""
        for tier in ["HIGH", "MEDIUM", "SPECULATIVE"]:
            d = m["by_conv"].get(tier)
            if d:
                wr = f"{d['win_rate']:.0%}" if d["win_rate"] is not None else "—"
                conv_rows += f"<tr><td>{tier}</td><td>{d['n']}</td><td>{wr}</td><td>{d['afg_brier']:.3f}</td></tr>"

        recent_rows = ""
        for r in resolved[:20]:
            hit = call_correct(r)
            hit_html = "<span class='good'>✓</span>" if hit else "<span class='bad'>✗</span>"
            outcome = "YES" if r["outcome"] == 1 else "NO"
            recent_rows += (f"<tr><td>{r['market'][:60]}</td><td>{r['category']}</td>"
                            f"<td>{r['kalshi_price']:.0%}</td><td>{r['afg_probability']:.0%}</td>"
                            f"<td>{outcome}</td><td>{hit_html}</td></tr>")

        body = f"""
      <div class="hero">
        <div class="metric">
          <div class="metric-label">AFG Brier Score</div>
          <div class="metric-value">{m['afg_brier']:.3f}</div>
          <div class="metric-sub">lower is better</div>
        </div>
        <div class="metric">
          <div class="metric-label">Kalshi Market Brier</div>
          <div class="metric-value muted">{m['kalshi_brier']:.3f}</div>
          <div class="metric-sub">the crowd's accuracy</div>
        </div>
        <div class="metric">
          <div class="metric-label">Win Rate</div>
          <div class="metric-value">{m['win_rate']:.0%}</div>
          <div class="metric-sub">{m['n']} resolved calls</div>
        </div>
      </div>
      <p class="delta {delta_class}">AFG {delta_word} the market by {abs(m['skill_delta']):.3f} Brier points.</p>

      <h2>Brier Score by Category</h2>
      <table><thead><tr><th>Category</th><th>Resolved</th><th>AFG Brier</th><th>Kalshi Brier</th><th>Win Rate</th></tr></thead>
      <tbody>{cat_rows}</tbody></table>

      <h2>Performance by Conviction Tier</h2>
      <table><thead><tr><th>Conviction</th><th>Resolved</th><th>Win Rate</th><th>AFG Brier</th></tr></thead>
      <tbody>{conv_rows}</tbody></table>

      <h2>Recent Resolved Calls</h2>
      <table><thead><tr><th>Market</th><th>Category</th><th>Kalshi</th><th>AFG</th><th>Outcome</th><th>Hit</th></tr></thead>
      <tbody>{recent_rows}</tbody></table>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AFG Performance Scorecard</title>
<style>
  :root {{ --navy:#17365D; --blue:#365F91; --green:#1F6F3D; --red:#A6231F; --line:#E2E8F0; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Georgia, 'Cambria', serif; max-width: 960px; margin: 0 auto; padding: 32px 20px;
         color: #1a202c; background: #fff; line-height: 1.5; }}
  header {{ text-align: center; border-bottom: 3px solid var(--navy); padding-bottom: 16px; margin-bottom: 8px; }}
  h1 {{ color: var(--navy); margin: 0; font-size: 2.1em; }}
  .subtitle {{ color: var(--blue); font-weight: bold; margin-top: 6px; }}
  .updated {{ color: #888; font-size: 0.85em; margin-top: 4px; }}
  h2 {{ color: var(--blue); border-bottom: 1px solid var(--blue); padding-bottom: 4px; margin-top: 36px; }}
  .hero {{ display: flex; gap: 16px; margin: 28px 0 8px; flex-wrap: wrap; }}
  .metric {{ flex: 1; min-width: 160px; border: 1px solid var(--line); border-radius: 10px;
             padding: 20px; text-align: center; background: #F8FAFC; }}
  .metric-label {{ font-size: 0.85em; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }}
  .metric-value {{ font-size: 2.4em; font-weight: bold; color: var(--navy); margin: 6px 0; }}
  .metric-sub {{ font-size: 0.8em; color: #999; }}
  .delta {{ font-size: 1.2em; font-weight: bold; text-align: center; margin: 8px 0 0; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 0.95em; }}
  th {{ background: #DCE6F1; text-align: left; padding: 10px; border: 1px solid #CBD5E0; color: var(--navy); }}
  td {{ padding: 10px; border: 1px solid #E2E8F0; }}
  tbody tr:nth-child(even) {{ background: #F8FAFC; }}
  .good {{ color: var(--green); font-weight: bold; }}
  .bad {{ color: var(--red); font-weight: bold; }}
  .muted {{ color: #888; }}
  footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--line);
            color: #888; font-size: 0.85em; text-align: center; }}
</style>
</head>
<body>
  <header>
    <h1>Axiom Forecasting Group</h1>
    <div class="subtitle">Performance Scorecard</div>
    <div class="updated">Last updated {updated}</div>
  </header>
  {body}
  <footer>
    Brier score measures forecast accuracy: 0 = perfect, 0.25 = coin flip, 1.0 = perfectly wrong.
    AFG publishes calibrated probability estimates on Kalshi prediction markets every Monday, Wednesday, and Friday.<br>
    This is research, not financial advice.
  </footer>
</body>
</html>"""

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    os.makedirs(DOCX_DIR, exist_ok=True)

    # INTEGRITY CHECK — print DB state before building anything.
    # Every "Resolved" call here must correspond to an actual Kalshi settlement.
    # If you see resolved calls and have NOT run 05_update_scorecard.py against
    # live Kalshi data first, STOP and run it now before proceeding.
    with get_conn() as conn:
        n_open = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='Open'").fetchone()[0]
        n_resolved = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='Resolved'").fetchone()[0]
        n_total = n_open + n_resolved
    print(f"=== SCORECARD INTEGRITY CHECK ===")
    print(f"  Total logged predictions : {n_total}")
    print(f"  Open (unresolved)        : {n_open}")
    print(f"  Resolved (will publish)  : {n_resolved}")
    if n_resolved > 0:
        print(f"  WARNING: {n_resolved} resolved calls will appear in the scorecard.")
        print(f"  Confirm each resolved call settled on Kalshi before publishing.")
    else:
        print(f"  Scorecard will show: No resolved predictions yet.")
    print(f"=================================")

    resolved = load_resolved()
    m = compute_metrics(resolved)

    docx_path = f"{DOCX_DIR}/AFG_Scorecard_{date.today().isoformat()}.docx"
    build_docx(resolved, m, docx_path)
    build_website(resolved, m, WEB_DIR)

    print(f"Wrote {docx_path}")
    print(f"Wrote {WEB_DIR}/index.html  (GitHub Pages site)")
    if m:
        print(f"  {m['n']} resolved calls | AFG Brier {m['afg_brier']:.3f} vs Kalshi {m['kalshi_brier']:.3f}")
    else:
        print("  No resolved calls yet — scorecard will populate as markets settle.")


if __name__ == "__main__":
    main()
