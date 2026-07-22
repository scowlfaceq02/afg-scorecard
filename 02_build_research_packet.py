"""
02_build_research_packet.py — Phase 2, reads data/raw_markets.xlsx (Phase 1's
output) and formats it into a structured research packet: one section per
category, each market's price/volume/ticker, and category-specific analytical
instructions encoding AFG's established methodology.

This packet is what Phase 3 hands to Claude (via chat paste today, or via
API later) -- so it carries both the data AND the standing house rules in one
self-contained file, rather than depending on conversation memory alone.

Run:
    python 02_build_research_packet.py
"""

import pandas as pd
from datetime import date

INPUT_PATH = "data/raw_markets.xlsx"
OUTPUT_PATH = "data/research_packet.md"

# Category-specific research instructions, encoding AFG's standing methodology.
# These print once per category section, not once per market.
CATEGORY_INSTRUCTIONS = {
    "Sports": (
        "- Evaluate injuries, rotations, and current form for the named teams/players.\n"
        "- Cross-reference Fangraphs (or the sport-appropriate advanced-stats source) and current betting odds.\n"
        "- Apply the standing favorite/prestige-premium fade: reigning champions, blue-blood programs, "
        "and heavy favorites in large fields are systematically overpriced by public money -- "
        "haircut accordingly unless current form strongly overrides it.\n"
        "- For soccer markets specifically, treat draw outcomes as a standing underpriced prior.\n"
        "- Run or reference simulations where available (e.g. season/tournament Monte Carlo projections)."
    ),
    "Politics": (
        "- Evaluate current polling, legal/procedural status, and relevant historical base rates "
        "for similar political events.\n"
        "- Apply the standing novelty/retail-inflation fade: narrative-driven, low-probability contracts "
        "(alien disclosure, viral scenarios, etc.) systematically run rich on attention rather than fundamentals.\n"
        "- Check for fast-moving real-world developments (search current news) that the static price pull "
        "may not yet reflect -- geopolitical and legal situations can move faster than Kalshi repricing.\n"
        "- Consider incumbency/continuity base rates for personnel and succession questions."
    ),
    "Economics": (
        "- Cross-reference current Fed communications, the most recent dot plot, and CME FedWatch-style "
        "market-implied probabilities.\n"
        "- Apply historical base rates for the specific macro indicator in question (rate paths, CPI prints, "
        "labor data surprises).\n"
        "- Consider the cross-asset implications explicitly -- Fed path affects crypto and equity risk appetite, "
        "energy/geopolitical shocks affect inflation expectations.\n"
        "- Flag narrative-driven macro scenario contracts (e.g. viral thesis-based markets) for the same "
        "novelty-fade discipline applied in Politics."
    ),
    "Culture": (
        "- Evaluate release schedules, studio/publisher track records, and award-season dynamics.\n"
        "- Apply the delay-history discipline: studios/developers with repeated slips (e.g. Rockstar) "
        "warrant haircuts on on-time release contracts.\n"
        "- Fade pre-release favorite premiums in award markets -- early front-runners for Oscars/GOTY "
        "are systematically overpriced relative to historical base rates of wire-to-wire favorites.\n"
        "- Casting/announcement markets are rumor-driven -- front-runner churn is the historical norm; "
        "unconfirmed reporting caps conviction at MEDIUM."
    ),
    "Weather": (
        "- CRITICAL: cross-reference the specific Kalshi settlement station for each ticker against the "
        "broader regional forecast -- settlement stations (often airport tarpac readings) can differ "
        "meaningfully from metro-area forecasts (e.g. LAX runs cooler than downtown LA; Miami airport has "
        "run hotter than model forecasts in observed sessions).\n"
        "- Apply base-rate anchoring for tail-risk/disaster markets (e.g. earthquake, hurricane magnitude) -- "
        "these are usually overpriced relative to historical USGS/NOAA base rates.\n"
        "- Check current NOAA/drought-monitor/hurricane-tracking data before assigning conviction."
    ),
}


def format_row(row, number):
    kalshi_pct = f"{row['yes_ask_dollars']:.0%}" if pd.notna(row.get("yes_ask_dollars")) else "N/A"
    volume = row.get("volume_fp", 0)
    volume_str = f"${volume:,.0f}"
    return (
        f"{number}. **Market:** {row['title']}\n"
        f"   **Ticker:** {row['ticker']}\n"
        f"   **Kalshi:** {kalshi_pct}\n"
        f"   **Volume:** {volume_str}\n"
    )


def build_packet():
    df = pd.read_excel(INPUT_PATH)
    if df.empty:
        raise ValueError(f"{INPUT_PATH} is empty -- run 01_pull_markets.py first.")

    lines = [
        "# AFG Daily Research Packet",
        f"### {date.today().isoformat()}",
        "",
        "For each market below: compare AFG probability to Kalshi's implied probability, "
        "compute Edge Score (AFG - Kalshi), assign conviction (HIGH/MEDIUM/SPECULATIVE), "
        "and recommend BUY YES / BUY NO / NO TRADE. Apply the category-specific research "
        "instructions and AFG's standing methodology throughout.",
        "",
    ]

    # Preserve a consistent category order rather than whatever order pandas groups them in
    category_order = ["Sports", "Politics", "Economics", "Culture", "Weather"]
    categories_present = [c for c in category_order if c in df["category"].unique()]

    for category in categories_present:
        subset = df[df["category"] == category].sort_values("volume_fp", ascending=False)
        lines.append(f"## {category.upper()}")
        lines.append("")
        lines.append("**Research Instructions:**")
        lines.append(CATEGORY_INSTRUCTIONS.get(category, "- Evaluate using standard AFG methodology."))
        lines.append("")
        for i, (_, row) in enumerate(subset.iterrows(), start=1):
            lines.append(format_row(row, i))
        lines.append("")

    packet = "\n".join(lines)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(packet)

    print(f"Wrote research packet to {OUTPUT_PATH} ({len(df)} markets across {len(categories_present)} categories)")
    return packet


if __name__ == "__main__":
    build_packet()
