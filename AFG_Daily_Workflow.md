# AFG Automated Workflow — Monday / Wednesday / Friday

**~90% automated. Your only manual steps: run the analysis in chat (your IP), review it, and push to GitHub.**
Everything else — the market pull, packet build, report generation, prediction logging, scorecard math, Word scorecard, and website — runs by script.

Start every session in the project folder:
```
cd C:\Users\qwhit\AFG
```

---

## The full cycle at a glance

| # | Step | Command | Automated? |
|---|------|---------|-----------|
| 1 | Pull top-5 markets x 5 categories from Kalshi | `python3 01_pull_markets.py` | Fully |
| 2 | Build research packet | `python3 02_build_research_packet.py` | Fully |
| 3 | Copy packet to clipboard + make draft files | `python3 03_run_claude.py` | Fully |
| 4 | **Analysis** — paste packet into chat, get calls | *(in chat)* | Manual (your IP) |
| 5 | **Review** — fill/approve the two draft files | *(your edit)* | Manual (the gate) |
| 6 | Build report (docx + xlsx + Substack brief) | `python3 04_build_report.py` | Fully |
| 7 | Log this cycle's calls into the scorecard DB | `python3 045_log_predictions.py` | Fully |
| 8 | Resolve yesterday's settled markets | `python3 05_update_scorecard.py` | Fully |
| 9 | Build the scorecard (Word doc + website) | `python3 06_build_scorecard.py` | Fully |
| 10 | Publish scorecard to the web | `git add -A && git commit -m "update" && git push` | Manual (one command) |

Steps 1-3 and 6-9 can be chained into a single `.bat` file (see bottom).

---

## MONDAY / WEDNESDAY / FRIDAY — the routine

### Part A — Generate the analysis (Steps 1-5)

```
python3 01_pull_markets.py
```
Runs ~20-30 min unattended. Success: `Done: ~6,120/6,147 series succeeded` + a top-5-per-category preview. Eyeball it against Kalshi's site.

```
python3 02_build_research_packet.py
python3 03_run_claude.py
```
The packet is now on your clipboard and two draft files exist in `data\`.

**Step 4 — Analysis (in chat):** Paste the packet (Ctrl+V) into your AFG Research Director chat. Ask for the full analysis: 25 calls plus Executive Summary, category narratives, Cross-Asset Themes, Contrarian Positioning, and Publication Note. Best practice: ask the chat to hand back the two finished files (`approved_predictions.csv` and `approved_narrative.md`) as downloads so there's zero transcription.

**Step 5 — Review (the gate):** Read both files. Change any call you disagree with. Delete rows for any market with a data-quality problem (note it in the Publication Note). Save as:
```
data\approved_predictions.csv
data\approved_narrative.md
```

### Part B — Build everything (Steps 6-9)

```
python3 04_build_report.py
python3 045_log_predictions.py
python3 05_update_scorecard.py
python3 06_build_scorecard.py
```
This produces, in order: the report + Substack brief, logs today's calls for future scoring, resolves any markets that settled since last cycle, and rebuilds the scorecard (Word doc AND website).

### Part C — Publish (Step 10)

Substack: paste `reports\AFG_Intelligence_Brief_<date>_Substack.md` into the composer, publish.

Scorecard website — one command:
```
git add -A && git commit -m "scorecard update <date>" && git push
```
Your live scorecard updates within ~1 minute at your GitHub Pages URL.

---

## ONE-TIME SETUP — the GitHub Pages scorecard site

You do this once. After that, Step 10 is the only web action per cycle.

1. Create a free GitHub account at github.com.
2. Create a new **public** repository named `afg-scorecard`.
3. In your `AFG` folder, initialize git and connect it:
```
git init
git add -A
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOURNAME/afg-scorecard.git
git push -u origin main
```
4. On GitHub: repo **Settings -> Pages -> Source** -> select branch `main`, folder `/docs`, Save.
5. Your scorecard is now live at `https://YOURNAME.github.io/afg-scorecard/` — share this link everywhere: Substack bio, every brief's footer, social. It auto-updates on every `git push`.

The `docs/` folder (with `index.html` and `.nojekyll`) is already built and ready — GitHub Pages serves it automatically.

---

## Growing subscribers with the scorecard

- **Put the live URL in every Substack post footer** and your bio. Social proof is the entire pitch for a research product — let the Brier score do the selling.
- **Monthly recap post** (free/public): "AFG beat the market by X Brier points this month across Y calls." The website makes this a screenshot, not a spreadsheet.
- **Lead with the skill delta**, not just win rate — "beating the market's own implied odds" is the credible, checkable claim that converts free readers to paid.

---

## Optional: chain the scripts into one click

Create `run_afg_full.bat` in your `AFG` folder:
```bat
@echo off
cd /d C:\Users\qwhit\AFG
echo === STEP 1: Pull markets ===
python3 01_pull_markets.py
echo === STEP 2: Build packet ===
python3 02_build_research_packet.py
echo === STEP 3: Prep handoff ===
python3 03_run_claude.py
echo.
echo *** NOW: paste the packet into chat, fill in the two approved files, then run run_afg_publish.bat ***
pause
```

And `run_afg_publish.bat` for after your review:
```bat
@echo off
cd /d C:\Users\qwhit\AFG
python3 04_build_report.py
python3 045_log_predictions.py
python3 05_update_scorecard.py
python3 06_build_scorecard.py
echo.
echo *** Report, scorecard, and website built. Now git push. ***
pause
```

That collapses the whole cycle to: double-click one file, do your analysis + review, double-click the second file, then one `git push`.

---

## What each output is for

| File | Purpose |
|------|---------|
| `reports\AFG_Research_Report_<date>.docx` | Institutional report — your records / clients |
| `data\final_report.xlsx` | Analysis + Volume Verification sheets |
| `reports\AFG_Intelligence_Brief_<date>_Substack.md` | Public brief — paste into Substack |
| `reports\AFG_Scorecard_<date>.docx` | Word scorecard — your records |
| `docs\index.html` | Live public scorecard website |
| `afg_scorecard.db` | The prediction ledger — **back this up weekly** (one file) |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `can't open file` | You're not in `C:\Users\qwhit\AFG`. Run `cd C:\Users\qwhit\AFG` first. |
| Step 1 shows a few `WARNING: failed to fetch` | Normal — under ~1% from rate limiting. |
| Scorecard says "No resolved calls yet" | Expected until markets you've logged actually settle. Populates over time. |
| A call never appears in the scorecard | It was logged without a ticker. Future pulls capture tickers automatically. |
| `git push` asks for login | First push per machine — use a GitHub personal access token as the password. |
| Website didn't update | Confirm the push succeeded and GitHub Pages is set to `/docs`. Give it ~1 min. |
