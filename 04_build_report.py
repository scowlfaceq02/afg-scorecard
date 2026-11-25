"""
04_build_report.py — Phase 4. Reads the two files YOU approved after review
(data/approved_predictions.csv and data/approved_narrative.md) and produces:

  - reports/AFG_Research_Report_<date>.docx  (locked institutional template)
  - data/final_report.xlsx                    (raw data backup)
  - reports/AFG_Substack_Post_<date>.md   (free teaser: summary + top 3, no edges)
  - reports/AFG_Twitter_Post_<date>.txt   (top call + edge score + rationale)

This script refuses to run if either approved file is missing -- that's the
checkpoint gate. Nothing before this point is allowed to skip your review.

Run:
    python 04_build_report.py
"""

import io
import os
import re
import sys
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker
import numpy as np
import pandas as pd
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

PREDICTIONS_PATH = "data/approved_predictions.csv"
NARRATIVE_PATH = "data/approved_narrative.md"
XLSX_OUTPUT_PATH = "data/final_report.xlsx"
REPORTS_DIR = "reports"

NAVY = RGBColor(0x17, 0x36, 0x5D)
BLUE = RGBColor(0x36, 0x5F, 0x91)
ACCENT = RGBColor(0x4F, 0x81, 0xBD)
GREEN = RGBColor(0x1F, 0x6F, 0x3D)
RED = RGBColor(0xA6, 0x23, 0x1F)
GRAY = RGBColor(0x80, 0x80, 0x80)
HEADER_FILL = "DCE6F1"
BORDER_COLOR = "A6A6A6"

FONT = "Cambria"
CATEGORY_ORDER = ["Sports", "Politics", "Economics", "Culture", "Weather"]

# Explicit DXA column widths (1440 dxa = 1 inch). Landscape Letter with 0.5"
# margins gives ~13680 dxa of usable width. The conviction table is indented
# -2880 dxa (2 inches left of the body margin) per the locked format.
# Column widths constrained to fit within the 10800 DXA text column
# (page 12240, margins 720 each side). The 7/17 reference used 14400 DXA
# which overflows in Word but clips in LibreOffice. These fit correctly in both.
# DXA widths fitted to 10800 DXA text column (portrait Letter, 0.5" margins).
# Recommendation: 2000 DXA -- enough for the full word "Recommendation" in 9.5pt bold Cambria.
# Market: 3200 DXA -- narrow enough to let the row fit on one page.
# Kalshi/AFG/Edge: 800 DXA each -- short numeric content.
OPP_COL_WIDTHS    = [3200, 1500, 800, 800, 800, 1700, 2000]      # sum=10800
CONTRA_COL_WIDTHS = [1440, 3060, 3780, 2520]                      # sum=10800
DASH_COL_WIDTHS   = [3600, 7200]                                   # sum=10800
TABLE_LEFT_SHIFT  = 0   # tables sized to fit text column; no indent needed



# ---------- date style ----------

def afg_date(d, with_year=False):
    """AFG house date style (adopted October 31st, 2026): 'November 2nd',
    or 'November 2nd, 2026' with the year. Never '2 November'."""
    n = d.day
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    s = f"{d.strftime('%B')} {n}{suffix}"
    return f"{s}, {d.year}" if with_year else s


# ---------- input loading & validation ----------

def require_approved_files():
    missing = [p for p in (PREDICTIONS_PATH, NARRATIVE_PATH) if not os.path.exists(p)]
    if missing:
        print("ERROR: Phase 4 requires both approved files to exist. Missing:")
        for m in missing:
            print(f"  {m}")
        print("\nThis is the review gate -- run 03_run_claude.py, fill in the draft")
        print("files, review them, and save your approved versions with these exact")
        print("filenames before running Phase 4.")
        sys.exit(1)


def load_predictions():
    df = pd.read_csv(PREDICTIONS_PATH)
    required = ["market", "category", "kalshi_price", "afg_probability", "conviction", "recommendation"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"{PREDICTIONS_PATH} is missing required columns: {missing_cols}")

    df["edge_score"] = df["afg_probability"] - df["kalshi_price"]
    # Rank by absolute edge; ties broken by conviction tier (HIGH > MEDIUM >
    # SPECULATIVE), then by CSV order. mergesort keeps the order stable.
    tier = {"HIGH": 0, "MEDIUM": 1, "SPECULATIVE": 2}
    df["_abs_edge"] = df["edge_score"].abs().round(4)
    df["_tier"] = df["conviction"].str.upper().map(tier).fillna(3)
    df = (df.sort_values(["_abs_edge", "_tier"], ascending=[False, True], kind="mergesort")
            .drop(columns=["_abs_edge", "_tier"]).reset_index(drop=True))
    return df


def parse_narrative():
    """
    Splits approved_narrative.md on '## ' headers into a dict of section name
    -> raw text. Also parses the Contrarian Positioning markdown table into a
    list of row dicts.
    """
    with open(NARRATIVE_PATH, encoding="utf-8") as f:
        text = f.read()

    sections = {}
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    # re.split with a capturing group interleaves: [prefix, header1, body1, header2, body2, ...]
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[header] = body

    contrarian_rows = []
    if "Contrarian Positioning" in sections:
        table_text = sections["Contrarian Positioning"]
        lines = [l.strip() for l in table_text.splitlines() if l.strip().startswith("|")]
        for line in lines[2:]:  # skip header row and separator row
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 4:
                contrarian_rows.append({
                    "category": cells[0], "consensus": cells[1],
                    "afg_view": cells[2], "position": cells[3],
                })

    return sections, contrarian_rows


# ---------- docx helpers ----------

def set_cell_shading(cell, hex_color):
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shading)


def set_cell_border_all(cell, color=BORDER_COLOR, size=2):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), color)
        borders.append(el)
    tcPr.append(borders)


def set_table_layout(table, col_widths_dxa, indent_dxa=0):
    """
    Matched byte-for-byte to the 2026-07-17 reference report:
      - NO table.autofit = False  (that adds tblLayout=fixed which clips cells)
      - NO tblInd
      - NO tblLayout element at all
      - Sets tblW to total DXA
      - Rebuilds tblGrid with per-column widths
      - Sets tcW on every cell

    The 7/17 reference has none of the "fixed layout" machinery that causes
    columns to clip their content -- it relies purely on tblW + gridCol + tcW.
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    tblPr = table._tbl.tblPr

    # Remove tblLayout (added by python-docx when autofit=False; absent in 7/17)
    for old_el in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old_el)

    # Remove tblInd (absent in 7/17)
    for old_el in tblPr.findall(qn("w:tblInd")):
        tblPr.remove(old_el)

    # Set tblW
    total = sum(col_widths_dxa)
    for old_el in tblPr.findall(qn("w:tblW")):
        tblPr.remove(old_el)
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(total))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    # Rebuild tblGrid
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        table._tbl.remove(grid)
    grid = OxmlElement("w:tblGrid")
    for w in col_widths_dxa:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        grid.append(gc)
    tblPr_idx = list(table._tbl).index(tblPr)
    table._tbl.insert(tblPr_idx + 1, grid)

    # Set minimal cell margins (top/bottom 40 DXA = 28pt/20) to compact row height
    tblCellMar = OxmlElement("w:tblCellMar")
    for edge, val in (("top","28"), ("bottom","28"), ("left","80"), ("right","80")):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), val)
        el.set(qn("w:type"), "dxa")
        tblCellMar.append(el)
    tblPr.append(tblCellMar)

    # Set tcW on every cell
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx >= len(col_widths_dxa):
                continue
            tcPr = cell._tc.get_or_add_tcPr()
            for old_el in tcPr.findall(qn("w:tcW")):
                tcPr.remove(old_el)
            tcW = OxmlElement("w:tcW")
            tcW.set(qn("w:w"), str(col_widths_dxa[idx]))
            tcW.set(qn("w:type"), "dxa")
            tcPr.append(tcW)


def style_run(run, size=10.5, bold=False, italic=False, color=None, underline=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.underline = underline
    if color is not None:
        run.font.color.rgb = color
    return run


def add_title_block(doc, report_date):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Axiom Forecasting Group")
    style_run(run, size=22, bold=True, color=NAVY)
    p.paragraph_format.space_after = Pt(2)

    # bottom rule under the title
    p_border = OxmlElement("w:pPr")
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "17365D")
    pbdr.append(bottom)
    p._p.get_or_add_pPr().append(pbdr)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p2.add_run("AFG Research Report")
    style_run(r1, size=12, bold=True, color=NAVY)
    r2 = p2.add_run(f"   |   {report_date}   |   Prediction Markets Research")
    style_run(r2, size=11, color=BLUE)
    p2.paragraph_format.space_after = Pt(8)


def add_section_heading(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    style_run(run, size=14, bold=True, color=BLUE, underline=True)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(4)
    return p


def add_body_paragraph(doc, text, italic=False, size=10.5):
    p = doc.add_paragraph()
    run = p.add_run(text)
    style_run(run, size=size, italic=italic)
    p.paragraph_format.space_after = Pt(4)
    return p


def recommendation_color(rec):
    rec = (rec or "").upper()
    if "BUY YES" in rec:
        return GREEN
    if "BUY NO" in rec:
        return RED
    return GRAY


def conviction_color(conv):
    conv = (conv or "").upper()
    if conv == "HIGH":
        return NAVY
    if conv == "MEDIUM":
        return BLUE
    return GRAY


def add_opportunities_table(doc, df):
    headers = ["Market", "Category", "Kalshi", "AFG", "Edge", "Conviction", "Recommendation"]
    table = doc.add_table(rows=1, cols=len(headers))

    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        style_run(run, size=9.5, bold=True, color=NAVY)
        set_cell_shading(cell, HEADER_FILL)
        set_cell_border_all(cell)

    for _, row in df.iterrows():
        tr = table.add_row()
        # Prevent any single row from splitting across a page break
        trPr = tr._tr.get_or_add_trPr()
        cantSplit = OxmlElement("w:cantSplit")
        cantSplit.set(qn("w:val"), "1")
        trPr.append(cantSplit)
        cells = tr.cells
        values = [
            row["market"],
            row["category"],
            f"{row['kalshi_price']:.0%}",
            f"{row['afg_probability']:.0%}",
            f"{row['edge_score']*100:+.0f}pp",
            row["conviction"],
            row["recommendation"],
        ]
        colors = [None, None, None, None, None, conviction_color(row["conviction"]), recommendation_color(row["recommendation"])]
        for i, (val, color) in enumerate(zip(values, colors)):
            cell = cells[i]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            style_run(run, size=9, bold=(color is not None), color=color)
            set_cell_border_all(cell)

    set_table_layout(table, OPP_COL_WIDTHS, indent_dxa=TABLE_LEFT_SHIFT)
    return table


def add_contrarian_table(doc, rows):
    headers = ["Category", "Consensus", "AFG View", "Position"]
    table = doc.add_table(rows=1, cols=len(headers))

    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        style_run(run, size=9.5, bold=True, color=NAVY)
        set_cell_shading(cell, HEADER_FILL)
        set_cell_border_all(cell)

    for row in rows:
        cells = table.add_row().cells
        values = [row["category"], row["consensus"], row["afg_view"], row["position"]]
        for i, val in enumerate(values):
            cell = cells[i]
            cell.text = ""
            color = recommendation_color(val) if i == 3 else None
            run = cell.paragraphs[0].add_run(val)
            style_run(run, size=9.5, bold=(i == 0 or color is not None), color=color)
            set_cell_border_all(cell)

    set_table_layout(table, CONTRA_COL_WIDTHS, indent_dxa=TABLE_LEFT_SHIFT)
    return table


def set_landscape(doc):
    """
    Portrait US Letter with 0.5" margins, matching the 2026-07-17 reference
    report. (Name kept for compatibility.) Tables are 14400 DXA and pulled
    left via negative indent so they sit centered on the page, extending
    past the text column on both sides -- this is what the reference does.
    """
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(0.5)
    section.right_margin = Inches(0.5)
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.5)


# ---------- assembly ----------

def add_dashboard_table(doc, stats):
    table = doc.add_table(rows=0, cols=2)
    for label, value in stats:
        cells = table.add_row().cells
        c0 = cells[0]
        c0.text = ""
        r0 = c0.paragraphs[0].add_run(label)
        style_run(r0, size=9.5, bold=True, color=NAVY)
        set_cell_border_all(c0)
        c1 = cells[1]
        c1.text = ""
        r1 = c1.paragraphs[0].add_run(str(value))
        style_run(r1, size=9.5)
        set_cell_border_all(c1)
    set_table_layout(table, DASH_COL_WIDTHS, indent_dxa=TABLE_LEFT_SHIFT)
    return table


# ---------- signature charts ----------

# AFG brand palette (hex strings for matplotlib)
_NAVY  = "#17365D"
_BLUE  = "#365F91"
_ACCENT = "#4F81BD"
_GREEN = "#1F6F3D"
_RED   = "#A6231F"
_LGRAY = "#F2F2F2"
_MGRAY = "#A6A6A6"
_TEXT  = "#1A1A1A"


def _chart_png(fig) -> bytes:
    """Render a matplotlib figure to PNG bytes and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    data = buf.read()
    plt.close(fig)
    return data


def _insert_chart_png(doc, png_bytes: bytes, width_inches: float = 6.5,
                      caption: str = ""):
    """Embed a PNG image into the docx, optionally with a caption."""
    buf = io.BytesIO(png_bytes)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(buf, width=Inches(width_inches))
    if caption:
        cap = doc.add_paragraph(caption)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_c = cap.runs[0] if cap.runs else cap.add_run(caption)
        style_run(run_c, size=8.5, italic=True, color=GRAY)


def build_probability_advantage_chart(df: pd.DataFrame) -> bytes:
    """
    Chart 1 — Where AFG Sees the Edge
    Horizontal grouped bar chart: AFG probability vs. Kalshi probability
    for all BUY positions, sorted by absolute edge descending.
    """
    buys = df[df["recommendation"].str.upper().str.contains("BUY", na=False)].copy()
    buys["abs_edge"] = (buys["afg_probability"] - buys["kalshi_price"]).abs()
    buys = buys.sort_values("abs_edge", ascending=True)  # ascending so top = top of chart

    if buys.empty:
        # Return a simple "no actionable calls" placeholder
        fig, ax = plt.subplots(figsize=(7, 1.5))
        ax.text(0.5, 0.5, "No actionable positions this cycle",
                ha="center", va="center", transform=ax.transAxes,
                color=_MGRAY, fontsize=10)
        ax.axis("off")
        return _chart_png(fig)

    labels = buys["market"].tolist()
    # CSV stores probabilities as decimals (0.0–1.0); convert to percentage
    kalshi_vals = (buys["kalshi_price"] * 100).tolist()
    afg_vals    = (buys["afg_probability"] * 100).tolist()
    n = len(labels)

    bar_h = 0.32
    y = np.arange(n)
    fig_h = max(2.5, n * 0.55 + 1.0)
    fig, ax = plt.subplots(figsize=(7.5, fig_h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars_k = ax.barh(y - bar_h / 2, kalshi_vals, bar_h, color=_ACCENT,
                     label="Kalshi", zorder=3)
    bars_a = ax.barh(y + bar_h / 2, afg_vals, bar_h, color=_NAVY,
                     label="AFG Estimate", zorder=3)

    # Edge labels on the AFG bars
    for bar, k, a in zip(bars_a, kalshi_vals, afg_vals):
        edge = a - k
        sign = "+" if edge >= 0 else ""
        ax.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                f"{sign}{edge:.0f}pp",
                va="center", ha="left", fontsize=7.5, color=_GREEN if edge > 0 else _RED,
                fontweight="bold", zorder=4)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5, color=_TEXT)
    ax.set_xlabel("Probability (%)", fontsize=8.5, color=_MGRAY)
    ax.set_xlim(0, min(100, max(max(kalshi_vals + afg_vals) + 14, 30)))
    ax.tick_params(axis="x", labelsize=8, colors=_MGRAY)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator())
    ax.grid(axis="x", color=_LGRAY, linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(_MGRAY)

    legend = ax.legend(fontsize=8, frameon=False, loc="lower right",
                       ncol=2, labelcolor=_TEXT)
    ax.set_title("Where AFG Sees the Edge", fontsize=11, fontweight="bold",
                 color=_NAVY, pad=10, loc="left")

    fig.tight_layout(pad=0.8)
    return _chart_png(fig)


def build_movement_tracker_chart(df: pd.DataFrame,
                                  history_path: str = "data/price_history.csv") -> bytes | None:
    """
    Chart 3 — The Market's Changing Expectations
    Line chart: Kalshi implied probability over time for each tracked market.
    AFG's current estimate shown as a dashed horizontal reference line per series.

    Returns None (no chart) if fewer than 2 dated snapshots exist in the log,
    so the first cycle after log_prices.py is seeded produces nothing — the
    chart becomes live on the second cycle (3 days later).
    """
    import os
    if not os.path.exists(history_path):
        return None

    hist = pd.read_csv(history_path, parse_dates=["log_date"])
    if hist.empty:
        return None

    # Only show markets that have at least 2 distinct dates in the log
    counts = hist.groupby("kalshi_ticker")["log_date"].nunique()
    tracked = counts[counts >= 2].index.tolist()
    if not tracked:
        return None  # not enough history yet — skip the chart entirely

    # Only plot the current cycle's active BUY positions (same set as Charts 1 and 3)
    current_tickers = df.loc[df["recommendation"].str.upper().str.contains("BUY", na=False),
                             "kalshi_ticker"].tolist()
    plot_tickers = [t for t in tracked if t in current_tickers]
    if not plot_tickers:
        return None

    # Build a label map from current cycle (market name is most up-to-date)
    label_map = dict(zip(df["kalshi_ticker"], df["market"]))
    afg_map   = dict(zip(df["kalshi_ticker"], df["afg_probability"] * 100))

    # Limit to 12 series max (the dataviz non-negotiable); pick by largest
    # absolute current edge to keep the most interesting markets
    df_edge = df.copy()
    df_edge["abs_edge"] = (df_edge["afg_probability"] - df_edge["kalshi_price"]).abs()
    df_edge = df_edge[df_edge["kalshi_ticker"].isin(plot_tickers)]
    df_edge = df_edge.sort_values("abs_edge", ascending=False)
    plot_tickers = df_edge["kalshi_ticker"].head(12).tolist()

    hist_subset = hist[hist["kalshi_ticker"].isin(plot_tickers)].copy()
    hist_subset["kalshi_price_pct"] = hist_subset["kalshi_price"].astype(float) * 100

    # Color palette: categorical order in fixed AFG brand hues
    palette = [_NAVY, _ACCENT, _RED, _GREEN, "#7F6084", "#C05A2A",
               "#1B7A8F", "#A89B2E", "#6C3483", "#2E8B57", "#C0392B", "#1A5276"]

    n_series = len(plot_tickers)
    fig_h = max(4.5, 3.5 + n_series * 0.15)
    fig, ax = plt.subplots(figsize=(7.5, fig_h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    used_colors = []
    for i, ticker in enumerate(plot_tickers):
        series = hist_subset[hist_subset["kalshi_ticker"] == ticker].sort_values("log_date")
        color = palette[i % len(palette)]
        used_colors.append(color)
        label = label_map.get(ticker, ticker)
        short = label if len(label) <= 28 else label[:26] + "…"

        ax.plot(series["log_date"], series["kalshi_price_pct"],
                color=color, linewidth=1.8, marker="o", markersize=5,
                zorder=3, label=short)

        # AFG reference line for this ticker (dashed, same color, lighter)
        afg_val = afg_map.get(ticker)
        if afg_val is not None:
            x_start = series["log_date"].min()
            x_end   = series["log_date"].max()
            ax.plot([x_start, x_end], [afg_val, afg_val],
                    color=color, linewidth=1.0, linestyle=":", alpha=0.55, zorder=2)

    ax.set_xlabel("Report Date", fontsize=8.5, color=_MGRAY)
    ax.set_ylabel("Kalshi Implied Probability (%)", fontsize=8.5, color=_MGRAY)
    ax.tick_params(labelsize=8, colors=_MGRAY)
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", color=_LGRAY, linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(_MGRAY)
    ax.spines["left"].set_color(_MGRAY)

    # Format x-axis dates compactly
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _pos: afg_date(mdates.num2date(v).date())))
    # One tick per logged cycle (thinned to at most 8 labels)
    _cycle_dates = sorted(hist_subset["log_date"].unique())
    _step = max(1, -(-len(_cycle_dates) // 8))
    ax.xaxis.set_major_locator(matplotlib.ticker.FixedLocator(
        [mdates.date2num(pd.Timestamp(d).to_pydatetime()) for d in _cycle_dates[::_step]]))

    # Legend outside plot area to avoid crowding
    legend = ax.legend(fontsize=7, frameon=False, loc="upper left",
                       bbox_to_anchor=(1.01, 1.0), borderaxespad=0,
                       labelcolor=_TEXT, ncol=1)

    # Dotted-line note in subtitle
    ax.set_title("The Market's Changing Expectations\n"
                 "Solid = Kalshi price · Dotted = AFG estimate",
                 fontsize=10, fontweight="bold", color=_NAVY, pad=10, loc="left",
                 linespacing=1.6)

    fig.tight_layout(pad=0.8)
    return _chart_png(fig)


def build_mispricing_matrix_chart(df: pd.DataFrame) -> bytes:
    """
    Chart 2 — Mapping the Market's Blind Spots
    Scatter plot: Kalshi probability (x) vs. AFG probability (y).
    The 45° diagonal = fair value. Points above = AFG more bullish (BUY YES).
    Points below = AFG more bearish (BUY NO). Color-coded by recommendation.
    """
    plot_df = df[df["recommendation"].str.upper().str.contains("BUY", na=False)].copy()
    if plot_df.empty:
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.text(0.5, 0.5, "No actionable positions this cycle",
                ha="center", va="center", transform=ax.transAxes,
                color=_MGRAY, fontsize=10)
        ax.axis("off")
        return _chart_png(fig)

    rec_upper = plot_df["recommendation"].str.upper()
    colors = [_GREEN if "YES" in r else _RED for r in rec_upper]

    # CSV stores probabilities as decimals (0.0–1.0); convert to percentage
    x = (plot_df["kalshi_price"] * 100).tolist()
    y_vals = (plot_df["afg_probability"] * 100).tolist()
    labels = plot_df["market"].tolist()

    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Diagonal fair-value line — cap at 100 (probabilities in %)
    lim_max = min(100, max(max(x + y_vals) + 12, 30))
    ax.plot([0, lim_max], [0, lim_max], color=_MGRAY, linewidth=1.2,
            linestyle="--", zorder=1, label="Fair Value (AFG = Kalshi)")

    # Shading: above diagonal = AFG more bullish; below = AFG more bearish
    ax.fill_between([0, lim_max], [0, lim_max], [lim_max, lim_max],
                    color=_GREEN, alpha=0.04, zorder=0)
    ax.fill_between([0, lim_max], [0, 0], [0, lim_max],
                    color=_RED, alpha=0.04, zorder=0)

    sc = ax.scatter(x, y_vals, c=colors, s=90, zorder=3,
                    edgecolors="white", linewidths=0.8)

    # Short labels with the edge appended, e.g. "Callum Turner · Bond  −15".
    # An optional chart_label column in approved_predictions.csv overrides
    # the automatic label for any row.
    edges = [a - k for a, k in zip(y_vals, x)]
    overrides = (plot_df["chart_label"].fillna("").astype(str).tolist()
                 if "chart_label" in plot_df.columns else [""] * len(labels))
    texts = []
    for lbl, ov, e in zip(labels, overrides, edges):
        base = ov.strip() or _chart_label(lbl)
        texts.append(f"{base}  {'+' if e > 0 else '−'}{abs(e):.0f}")

    ax.set_xlim(0, lim_max)
    ax.set_ylim(0, lim_max)
    ax.set_xlabel("Kalshi Implied Probability (%)", fontsize=9, color=_MGRAY)
    ax.set_ylabel("AFG Probability Estimate (%)", fontsize=9, color=_MGRAY)
    ax.tick_params(labelsize=8, colors=_MGRAY)
    ax.grid(color=_LGRAY, linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(_MGRAY)
    ax.spines["left"].set_color(_MGRAY)

    yes_patch = mpatches.Patch(color=_GREEN, label="BUY YES (AFG more bullish)")
    no_patch  = mpatches.Patch(color=_RED,   label="BUY NO  (AFG more bearish)")
    fair_line = plt.Line2D([0], [0], color=_MGRAY, linewidth=1.2,
                           linestyle="--", label="Fair Value")
    # Legend sits below the plot so it never competes with point labels
    ax.legend(handles=[yes_patch, no_patch, fair_line], fontsize=7.5,
              frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.09),
              ncol=3, labelcolor=_TEXT)

    ax.set_title("Mapping the Market's Blind Spots", fontsize=11,
                 fontweight="bold", color=_NAVY, pad=10, loc="left")
    ax.text(0, 1.005, "Label = market and AFG edge in points. Distance from the dashed line = size of the disagreement.",
            transform=ax.transAxes, fontsize=7, color=_MGRAY, va="bottom")

    fig.tight_layout(pad=0.8)
    # Place labels last, once the axes geometry is final
    _place_point_labels(fig, ax, x, y_vals, texts,
                        priority=[abs(e) for e in edges])
    return _chart_png(fig)


_SERIES_CONTEXT = [
    ("Next James Bond", "Bond"), ("Heisman", "Heisman"), ("NFL MVP", "MVP"),
    ("Game Awards", "GOTY"), ("Oscar Best Picture", "Best Picture"),
    ("NFL Champion", "Super Bowl"), ("NBA Champion", "NBA title"),
    ("College Football Champion", "CFP title"),
    ("Trump administration departures", "leaves in 2026"),
    ("Dancing with the Stars", "DWTS"),
]
_GENERIC_TAILS = ("hike", "cut", "hold", "exactly", "more than", "above",
                  "below", "yes", "no ")


def _chart_label(market: str) -> str:
    """Short, house-style label for a chart point, wrapped to two lines max."""
    import textwrap
    m = market.strip().rstrip("?").strip()
    m = re.sub(r"before Jan 1 (\d{4})", r"before \1", m)        # house date style
    m = re.sub(r"^Will (the )?(.*?)( happen)?$", r"\2", m)
    if "—" in m:
        head, tail = [s.strip() for s in m.split("—", 1)]
        context = next((c for key, c in _SERIES_CONTEXT if key in head), None)
        if context and not tail.lower().startswith(_GENERIC_TAILS):
            m = f"{tail} · {context}"
        else:
            m = f"{head}: {tail}"
    m = m[:1].upper() + m[1:]
    lines = textwrap.wrap(m, width=26)
    if len(lines) > 2:
        lines = [lines[0], (lines[1][:24].rstrip() + "…")]
    return "\n".join(lines)


def _place_point_labels(fig, ax, xs, ys, texts, priority):
    """
    Deterministic, dependency-free label placement. Labels are placed in
    order of priority (largest edge first). For each, candidate positions
    around the point are tried at increasing distance; the first one that
    stays inside the plot and clears every point and every placed label wins.
    Labels set away from their point get a thin leader line.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    px = fig.dpi / 72.0
    ax_box = ax.get_window_extent(renderer)
    pts = ax.transData.transform(list(zip(xs, ys)))
    r = 6 * px                                   # marker radius plus margin
    point_boxes = [(p[0] - r, p[1] - r, p[0] + r, p[1] + r) for p in pts]

    # (dx, dy) unit directions with matching text alignment
    dirs = [(1, 0, "left", "center"), (-1, 0, "right", "center"),
            (1, 1, "left", "bottom"), (-1, 1, "right", "bottom"),
            (1, -1, "left", "top"), (-1, -1, "right", "top"),
            (0, 1, "center", "bottom"), (0, -1, "center", "top")]
    radii = [7, 14, 22, 32, 44, 58]

    def overlap(a, b, pad=2 * px):
        w = min(a[2], b[2]) - max(a[0], b[0]) + pad
        h = min(a[3], b[3]) - max(a[1], b[1]) + pad
        return w * h if (w > 0 and h > 0) else 0.0

    placed = []
    order = sorted(range(len(texts)), key=lambda i: -priority[i])
    for i in order:
        best = None
        for rad in radii:
            for dx, dy, ha, va in dirs:
                norm = (dx * dx + dy * dy) ** 0.5
                off = (dx / norm * rad, dy / norm * rad)
                ann = ax.annotate(texts[i], (xs[i], ys[i]), xytext=off,
                                  textcoords="offset points", fontsize=7,
                                  color=_TEXT, ha=ha, va=va, zorder=5,
                                  linespacing=1.15)
                bb = ann.get_window_extent(renderer)
                box = (bb.x0, bb.y0, bb.x1, bb.y1)
                outside = (box[0] < ax_box.x0 or box[2] > ax_box.x1 or
                           box[1] < ax_box.y0 or box[3] > ax_box.y1)
                cost = (1e9 if outside else 0.0)
                cost += sum(overlap(box, b) for b in placed)
                cost += sum(overlap(box, pb) for j, pb in enumerate(point_boxes) if j != i)
                ann.remove()
                if best is None or cost < best[0]:
                    best = (cost, off, ha, va, box, rad)
                if cost == 0:
                    break
            if best and best[0] == 0:
                break
        cost, off, ha, va, box, rad = best
        arrow = (dict(arrowstyle="-", color=_MGRAY, lw=0.6,
                      shrinkA=1, shrinkB=5) if rad >= 14 else None)
        ax.annotate(texts[i], (xs[i], ys[i]), xytext=off,
                    textcoords="offset points", fontsize=7, color=_TEXT,
                    ha=ha, va=va, zorder=5, linespacing=1.15, arrowprops=arrow)
        placed.append(box)


def build_docx(df, sections, contrarian_rows, report_date, output_path):
    doc = Document()
    set_landscape(doc)

    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(10.5)

    add_title_block(doc, report_date)

    add_section_heading(doc, "Executive Summary")
    add_body_paragraph(doc, sections.get("Executive Summary", ""))

    # Executive Dashboard stats, computed from the approved predictions
    # Count screened Kalshi EVENTS, not rows: two strikes of one event (e.g. two
    # Hormuz dates, two Bond actors) are one screened market, so counting rows
    # would understate the number of markets excluded.
    _events = df["kalshi_ticker"].astype(str).map(
        lambda t: t.rsplit("-", 1)[0] if t.count("-") >= 2 else t)
    n_published = min(25, _events.nunique())
    # Threshold rule (adopted 21 Oct 2026): open a new position at >= 3pp,
    # hold an open one while the gap is >= 2pp, reopen a closed one at >= 4pp.
    # A held position can therefore be actionable at 2pp and a closed one can be
    # NO TRADE at 3pp, so count the published BUY calls, not raw edges.
    n_actionable = int(df["recommendation"].str.upper().str.contains("BUY", na=False).sum())
    n_high = int((df["conviction"].str.upper() == "HIGH").sum())
    excluded_note = sections.get("Publication Note", "")
    # user records the screened/excluded counts in the narrative; fall back to published count
    add_section_heading(doc, "Executive Dashboard")
    add_dashboard_table(doc, [
        ("Markets screened", sections.get("Markets Screened", "25 (5 categories × 5)")),
        ("Markets excluded for data quality", 25 - n_published),
        ("Actionable calls (open ≥ 3pp, hold ≥ 2pp, reopen ≥ 4pp)", n_actionable),
        ("HIGH conviction calls", n_high),
    ])

    add_section_heading(doc, "10 Highest Conviction Opportunities")
    add_body_paragraph(doc, "Top 10, ranked by absolute AFG Edge Score (AFG Probability minus Kalshi implied probability).", italic=True, size=9)
    # The conviction table lists ACTIONABLE opportunities only. A NO TRADE is
    # by definition not an opportunity, so it is excluded here even when its
    # raw edge score would rank it in the top ten. NO TRADE positions remain
    # documented in the category narratives and the Publication Note.
    actionable = df[df["recommendation"].str.upper().str.contains("BUY", na=False)]
    add_opportunities_table(doc, actionable.head(10))

    for category in CATEGORY_ORDER:
        if category in sections and sections[category]:
            add_section_heading(doc, category)
            add_body_paragraph(doc, sections[category])

    if "Cross-Asset Themes" in sections:
        add_section_heading(doc, "Cross-Asset Themes")
        for line in sections["Cross-Asset Themes"].splitlines():
            line = line.strip().lstrip("-").strip()
            if line:
                p = doc.add_paragraph(style="List Bullet")
                run = p.add_run(line)
                style_run(run, size=10.5)

    if contrarian_rows:
        add_section_heading(doc, "Contrarian Positioning")
        add_contrarian_table(doc, contrarian_rows)

    # --- Signature Charts (inserted after Contrarian Positioning) ---
    add_section_heading(doc, "AFG Signature Charts")

    png1 = build_probability_advantage_chart(df)
    _insert_chart_png(doc, png1, width_inches=6.5,
                      caption="Chart 1 — Where AFG Sees the Edge  |  "
                              "AFG Probability vs. Kalshi Implied Probability for all active BUY positions.")

    doc.add_paragraph()  # spacer

    png3 = build_movement_tracker_chart(df)
    if png3 is not None:
        _insert_chart_png(doc, png3, width_inches=6.5,
                          caption="Chart 2 — The Market's Changing Expectations  |  "
                                  "Solid lines: Kalshi implied probability across Mon/Wed/Fri cycles. "
                                  "Dotted lines: current AFG estimate.")
        doc.add_paragraph()  # spacer

    png2 = build_mispricing_matrix_chart(df)
    _insert_chart_png(doc, png2, width_inches=5.5,
                      caption="Chart 3 — Mapping the Market's Blind Spots  |  "
                              "Points above the diagonal: AFG more bullish than Kalshi. "
                              "Points below: AFG more bearish. Distance from the line = magnitude of disagreement.")

    if excluded_note:
        add_section_heading(doc, "Publication Note")
        add_body_paragraph(doc, excluded_note, italic=True, size=9.5)

    doc.save(output_path)


def build_xlsx(df, output_path, raw_markets_path="data/raw_markets.xlsx"):
    """
    Three sheets:
      - 'Analysis'             : the approved calls
      - 'Volume Verification'  : top 5 by TRADING VOLUME per category, taken
                                 straight from the Phase 1 pull, so you can
                                 open Kalshi's site side by side and confirm
                                 the rankings match.
      - 'Category Totals'      : total + top-5 volume per category.

    If raw_markets.xlsx is missing this now RAISES rather than silently
    skipping the volume sheets (which previously produced a workbook with no
    volume data and no warning).
    """
    export_df = df.copy()
    export_df["kalshi_price"] = export_df["kalshi_price"].map(lambda x: f"{x:.1%}")
    export_df["afg_probability"] = export_df["afg_probability"].map(lambda x: f"{x:.1%}")
    export_df["edge_score"] = export_df["edge_score"].map(lambda x: f"{x*100:+.1f}pp")

    if not os.path.exists(raw_markets_path):
        raise FileNotFoundError(
            f"{raw_markets_path} not found -- the Volume Verification sheet cannot be "
            f"built without it. Run 01_pull_markets.py before 04_build_report.py."
        )

    raw = pd.read_excel(raw_markets_path)
    if "volume_fp" not in raw.columns:
        raise ValueError(
            f"{raw_markets_path} has no 'volume_fp' column. Re-run 01_pull_markets.py."
        )

    raw["volume_fp"] = pd.to_numeric(raw["volume_fp"], errors="coerce").fillna(0)

    top5 = (
        raw.sort_values("volume_fp", ascending=False)
        .groupby("category", group_keys=False)
        .head(5)
        .sort_values(["category", "volume_fp"], ascending=[True, False])
        .reset_index(drop=True)
    )
    verify = pd.DataFrame({
        "Category": top5["category"],
        "Rank in Category": top5.groupby("category").cumcount() + 1,
        "Market": top5["title"],
        "Ticker": top5["ticker"],
        "Trading Volume": top5["volume_fp"].round(0).astype("int64"),
        "Kalshi Price": top5["yes_ask_dollars"],
    })

    totals = (
        raw.groupby("category")["volume_fp"]
        .agg(Markets_Found="count", Total_Volume="sum")
        .reset_index()
        .rename(columns={"category": "Category"})
    )
    top5_vol = top5.groupby("category")["volume_fp"].sum().reset_index()
    top5_vol.columns = ["Category", "Top5_Volume"]
    totals = totals.merge(top5_vol, on="Category", how="left")
    totals["Total_Volume"] = totals["Total_Volume"].round(0).astype("int64")
    totals["Top5_Volume"] = totals["Top5_Volume"].fillna(0).round(0).astype("int64")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name="Analysis", index=False)
        verify.to_excel(writer, sheet_name="Volume Verification", index=False)
        totals.to_excel(writer, sheet_name="Category Totals", index=False)

        # Real numeric currency formatting so volumes are sortable/verifiable
        for sheet, col, width in (("Volume Verification", "E", 18), ("Category Totals", "C", 18)):
            ws = writer.sheets[sheet]
            for cell in ws[col][1:]:
                cell.number_format = '$#,##0'
            ws.column_dimensions[col].width = width
        ws = writer.sheets["Category Totals"]
        for cell in ws["D"][1:]:
            cell.number_format = '$#,##0'
        ws.column_dimensions["D"].width = 18
        vv = writer.sheets["Volume Verification"]
        vv.column_dimensions["C"].width = 60
        vv.column_dimensions["D"].width = 32


def build_substack_post(df, sections, report_date, output_path):
    """
    Free Substack teaser. Deliberately withholds the analytical product:
      - thought-provoking title
      - Executive Summary
      - TOP 3 CALLS, market name + direction ONLY (no edge score, no rationale)
    Edge scores, conviction tiers and reasoning stay in the paid report.
    """
    top3 = df[df["recommendation"].str.upper().str.contains("BUY", na=False)].head(3)
    lead = top3.iloc[0]

    # Title is authored per cycle in the narrative under "## Substack Title".
    title = (sections.get("Substack Title") or "").strip()
    if not title:
        direction = "Overpricing" if lead["edge_score"] < 0 else "Underpricing"
        subject = lead["market"].split("—")[0].strip().rstrip("?")
        title = f"The Market Is {direction} {subject}"

    lines = [
        f"# {title}",
        "",
        f"*AFG Intelligence Brief — {report_date}*",
        "",
        "---",
        "",
        sections.get("Executive Summary", ""),
        "",
        "## Today's Top 3 Calls",
        "",
    ]

    for i, (_, r) in enumerate(top3.iterrows(), start=1):
        lines.append(f"**{i}. {r['market']}** — {r['recommendation']}")
        lines.append("")

    lines += [
        "---",
        "",
        "Edge scores, conviction tiers, full reasoning and the complete "
        "10-market conviction table are available to paid subscribers.",
        "",
        "[**Subscribe to AFG on Substack**](https://axiomforecastinggroup.substack.com) "
        "— research published every Monday, Wednesday, and Friday.",
        "",
        "Every AFG call is logged and scored against the market's own implied "
        "probability. Track the record here: "
        "**[AFG Forecast Accuracy Index](https://scowlfaceq02.github.io/afg-scorecard/)**",
        "",
        "*Research, not financial advice. Trade your own book.*",
        "",
        "— AFG Research",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_twitter_post(df, sections, report_date, output_path):
    """
    ENGAGEMENT FORMAT (adopted August 2026). NOT a BUY YES/NO announcement.

    Body copy is 150 characters or less and is authored per cycle in the
    narrative file under "## Twitter Post". It pulls ONE interesting
    observation from the research and opens with tension or a question so
    readers reply. Four rotating formats:
      (1) Probability Gap      (2) Forecasting Lesson
      (3) What the Market Is Missing   (4) Scorecard

    The old "AFG: <market> / Kalshi X% -> AFG Y% / BUY NO" format is
    deliberately gone. If the narrative omits a "## Twitter Post" section
    this function raises rather than silently falling back to the old
    format, because a silent fallback is how the wrong format shipped once
    already.
    """
    body = (sections.get("Twitter Post") or "").strip()
    if not body:
        raise ValueError(
            "approved_narrative.md is missing a '## Twitter Post' section. "
            "The engagement format requires per-cycle authored copy — there "
            "is no automatic fallback."
        )

    SCORECARD_URL = "https://scowlfaceq02.github.io/afg-scorecard/"
    SUBSTACK_URL  = "https://axiomforecastinggroup.substack.com/welcome"

    post = f"{body}\n\n📊 {SCORECARD_URL}\n📬 {SUBSTACK_URL}"

    # X counts every URL as 23 chars regardless of true length
    adjusted = post.replace(SCORECARD_URL, "x" * 23).replace(SUBSTACK_URL, "x" * 23)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"AFG TWITTER POST — {report_date}\n")
        f.write("=" * 60 + "\n")
        f.write("Paste the block below directly into X/Twitter.\n")
        f.write("=" * 60 + "\n\n")
        f.write(post)
        f.write("\n\n" + "=" * 60 + "\n")
        f.write(f"Body copy: {len(body)} chars (target <= 150)\n")
        f.write(f"Full post X-adjusted: {len(adjusted)} / 280\n")

    if len(body) > 150:
        print(f"  WARNING: Twitter body is {len(body)} chars, over the 150 target.")


def build_substack_note(sections, report_date, output_path):
    """
    Substack Note — published Mon/Wed/Fri alongside the research post.
    Same voice as the Twitter post but conversational: state the two
    probabilities, name the move, then pose the analytical question rather
    than answering it. Commentary, not advertisement.

    Authored per cycle in the narrative under "## Substack Note".
    """
    body = (sections.get("Substack Note") or "").strip()
    if not body:
        raise ValueError(
            "approved_narrative.md is missing a '## Substack Note' section."
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"AFG SUBSTACK NOTE — {report_date}\n")
        f.write("=" * 60 + "\n")
        f.write("Paste into Substack Notes. Link to today's post at the end.\n")
        f.write("=" * 60 + "\n\n")
        f.write(body)
        f.write("\n\n[link to today's Substack post]\n")
        f.write("\n" + "=" * 60 + "\n")


def main():
    require_approved_files()
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Auto-log prices for Chart 3 (Probability Movement Tracker).
    # Runs silently; failure does not block the report.
    try:
        import log_prices
        log_prices.main()
    except Exception as _lp_err:
        print(f"[log_prices] warning: {_lp_err}")

    df = load_predictions()
    sections, contrarian_rows = parse_narrative()
    report_date = afg_date(date.today(), with_year=True)
    file_date = date.today().isoformat()

    docx_path = f"{REPORTS_DIR}/AFG_Research_Report_{file_date}.docx"
    post_path    = f"{REPORTS_DIR}/AFG_Substack_Post_{file_date}.md"
    twitter_path = f"{REPORTS_DIR}/AFG_Twitter_Post_{file_date}.txt"
    note_path    = f"{REPORTS_DIR}/AFG_Substack_Note_{file_date}.txt"

    build_docx(df, sections, contrarian_rows, report_date, docx_path)
    build_xlsx(df, XLSX_OUTPUT_PATH)
    build_substack_post(df, sections, report_date, post_path)
    build_twitter_post(df, sections, report_date, twitter_path)
    build_substack_note(sections, report_date, note_path)

    print(f"Wrote {docx_path}")
    print(f"Wrote {XLSX_OUTPUT_PATH}")
    print(f"Wrote {post_path}")
    print(f"Wrote {twitter_path}")
    print(f"Wrote {note_path}")


if __name__ == "__main__":
    main()
