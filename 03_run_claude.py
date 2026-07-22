"""
03_run_claude.py — Phase 3, manual version. Keeps you fully in the loop:
this script does NOT call any AI API. It prepares everything so pasting into
your AFG Research Director chat and filling in the response is as low-
friction as possible, then stops -- your review is the checkpoint, not a
formality.

What this does:
  1. Confirms data/research_packet.md exists (run 02_build_research_packet.py first if not).
  2. Tries to copy the packet's contents to your clipboard automatically.
  3. Opens the packet in your default text/markdown viewer, as a fallback/backup.
  4. Pre-builds data/draft_predictions.csv using data/raw_markets.xlsx --
     market, category, ticker, price, and close date are already filled in;
     only afg_probability, conviction, and recommendation are left blank for
     you to fill in after Claude responds.

What you do next:
  1. Paste the packet (already on your clipboard) into your AFG Research
     Director chat.
  2. Get Claude's analysis for all 25 markets.
  3. Open data/draft_predictions.csv and fill in the three blank columns
     for each row.
  4. Review it. When you're satisfied, save your reviewed version as
     data/approved_predictions.csv -- Phase 4 will only read that exact file.

Run:
    python 03_run_claude.py
"""

import os
import sys
import pandas as pd
from datetime import date

PACKET_PATH = "data/research_packet.md"
RAW_MARKETS_PATH = "data/raw_markets.xlsx"
DRAFT_OUTPUT_PATH = "data/draft_predictions.csv"
NARRATIVE_TEMPLATE_PATH = "data/draft_narrative.md"

NARRATIVE_TEMPLATE = """## Executive Summary
[Paste Claude's executive summary paragraph(s) here]

## Sports
[Paste Claude's Sports narrative here]

## Politics
[Paste Claude's Politics narrative here]

## Economics
[Paste Claude's Economics narrative here]

## Crypto
[Paste Claude's Crypto narrative here]

## Weather
[Paste Claude's Weather narrative here]

## Cross-Asset Themes
- [First cross-asset connection]
- [Second cross-asset connection]
- [Third cross-asset connection]

## Contrarian Positioning
| Category | Consensus | AFG View | Position |
|---|---|---|---|
| Sports | [market consensus] | [AFG's contrarian view] | [BUY YES / BUY NO] |
| Economics | [market consensus] | [AFG's contrarian view] | [BUY YES / BUY NO] |
| Politics | [market consensus] | [AFG's contrarian view] | [BUY YES / BUY NO] |
| Crypto | [market consensus] | [AFG's contrarian view] | [Directional lean only -- Watch Only] |
| Weather | [market consensus] | [AFG's contrarian view] | [BUY YES / BUY NO] |

## Publication Note
[List which markets were excluded from publication this cycle and why -- e.g. "All five Crypto markets excluded for unconfirmed live pricing. Flagged items retained internally for follow-up." If nothing was excluded, write "No markets excluded this cycle."]
"""


def copy_to_clipboard(text):
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"  (clipboard copy failed: {e} -- not fatal, use the opened file instead)")
        return False


def open_in_default_app(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            os.system(f"open '{path}'")
        else:
            os.system(f"xdg-open '{path}'")
        return True
    except Exception as e:
        print(f"  (couldn't auto-open the file: {e} -- open it manually instead)")
        return False


def build_draft_template():
    df = pd.read_excel(RAW_MARKETS_PATH)
    report_date = date.today().isoformat()

    draft = pd.DataFrame({
        "market": df["title"],
        "category": df["category"],
        "kalshi_ticker": df["ticker"],
        "report_date": report_date,
        "kalshi_price": df["yes_ask_dollars"],
        "afg_probability": "",       # <-- fill in from Claude's response
        "conviction": "",            # <-- fill in from Claude's response
        "recommendation": "",        # <-- fill in from Claude's response
        "contract_close_date": df["close_time"].astype(str).str[:10] if "close_time" in df.columns else "",
    })

    draft.to_csv(DRAFT_OUTPUT_PATH, index=False)
    return draft


def main():
    if not os.path.exists(PACKET_PATH):
        print(f"ERROR: {PACKET_PATH} not found. Run 02_build_research_packet.py first.")
        sys.exit(1)
    if not os.path.exists(RAW_MARKETS_PATH):
        print(f"ERROR: {RAW_MARKETS_PATH} not found. Run 01_pull_markets.py first.")
        sys.exit(1)

    with open(PACKET_PATH, encoding="utf-8") as f:
        packet_text = f.read()

    copied = copy_to_clipboard(packet_text)
    opened = open_in_default_app(PACKET_PATH)

    draft = build_draft_template()

    with open(NARRATIVE_TEMPLATE_PATH, "w", encoding="utf-8") as f:
        f.write(NARRATIVE_TEMPLATE)

    print("\n" + "=" * 60)
    if copied:
        print("The research packet is now on your clipboard.")
    else:
        print("Clipboard copy wasn't available (pyperclip not installed --")
        print("run 'pip install pyperclip' to enable this next time).")
    if opened:
        print(f"{PACKET_PATH} has also been opened in your default app,")
        print("in case you'd rather copy it from there.")
    print("=" * 60)
    print(f"\nNext steps:")
    print(f"  1. Paste the packet into your AFG Research Director chat.")
    print(f"  2. Get Claude's full analysis: all {len(draft)} market calls, plus the")
    print(f"     Executive Summary, category narratives, Cross-Asset Themes, and")
    print(f"     Contrarian Positioning calls.")
    print(f"  3. Open {DRAFT_OUTPUT_PATH} -- it's pre-filled with market/ticker/price/")
    print(f"     close date for all {len(draft)} rows. Fill in just the three blank")
    print(f"     columns (afg_probability, conviction, recommendation) from Claude's answer.")
    print(f"  4. Open {NARRATIVE_TEMPLATE_PATH} -- fill in each bracketed section with")
    print(f"     Claude's prose (Executive Summary, category write-ups, Cross-Asset")
    print(f"     Themes, Contrarian Positioning table).")
    print(f"  5. Review both files. If a market shouldn't be published (data quality")
    print(f"     issue, etc.), delete its row from the CSV now -- that's the exclusion")
    print(f"     step, not a separate flag.")
    print(f"  6. When satisfied, save your reviewed versions as:")
    print(f"       data/approved_predictions.csv")
    print(f"       data/approved_narrative.md")
    print(f"     Phase 4 only reads those two exact filenames.")


if __name__ == "__main__":
    main()
