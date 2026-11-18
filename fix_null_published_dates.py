"""
fix_null_published_dates.py  --  restores missing publication dates (November 18th, 2026)
======================================================================================
diag_accuracy_match.py showed that row 235 (KXBOND-30-JAC, Jack Lowden, BUY NO at 8% against
12%) has no published_date and no close_date. 06_build_scorecard.py orders a contract's calls
by publication date, and SQLite sorts a missing date FIRST, so the builder skipped AFG's
November 16th BUY NO and scored the November 4th BUY YES instead: Lowden showed as Incorrect
when AFG's final call before settlement was correct. That is the whole 56% vs 60% gap.

This script finds EVERY active row with a missing published_date (not just row 235) and
restores the date only when the row matches exactly one call in AFG's published files for
November 13th, 16th and 18th, 2026 (same ticker, call, AFG probability and Kalshi price).
It fills a missing close_date from the same file. Rows it cannot match are listed and left
untouched.

Run from C:\\Users\\qwhit\\AFG\\ :
    python3 fix_null_published_dates.py          (preview, changes nothing)
    python3 fix_null_published_dates.py --apply  (makes the change)
Then run run_cycle.py again.
"""
import sqlite3
import sys

DB_PATH = "afg_scorecard.db"

# Every call AFG published on November 13th, 16th and 18th, 2026:
# [ticker, recommendation, afg_probability, kalshi_price, report_date, contract_close_date]
PUBLISHED = [
    ["KXSB-27-SF", "BUY NO", 0.13, 0.16, "2026-11-13", "2027-02-14"],
    ["KXSB-27-BUF", "BUY NO", 0.12, 0.15, "2026-11-13", "2027-02-14"],
    ["KXNCAAF-27-UGA", "BUY NO", 0.27, 0.31, "2026-11-13", "2027-01-15"],
    ["KXNBA-27-SAS", "NO TRADE", 0.21, 0.22, "2026-11-13", "2027-06-30"],
    ["KXNBA-27-OKC", "NO TRADE", 0.14, 0.13, "2026-11-13", "2027-06-30"],
    ["KXNFLMVP-27-JBUR", "BUY NO", 0.29, 0.33, "2026-11-13", "2027-02-12"],
    ["KXNFLMVP-27-JALL", "NO TRADE", 0.2, 0.21, "2026-11-13", "2027-02-12"],
    ["KXHEISMAN-27-JSMIT", "BUY NO", 0.25, 0.32, "2026-11-13", "2026-12-12"],
    ["KXHEISMAN-27-DMENS", "BUY NO", 0.25, 0.28, "2026-11-13", "2026-12-12"],
    ["KXHEISMAN-27-CCARR", "BUY YES", 0.22, 0.17, "2026-11-13", "2026-12-12"],
    ["KXCITRINI-28JUL01", "BUY NO", 0.1, 0.19, "2026-11-13", "2028-07-01"],
    ["KXRATECUTCOUNT-26DEC31-T0", "NO TRADE", 0.99, 0.98, "2026-11-13", "2026-12-31"],
    ["KXFEDDECISION-26DEC-H25", "NO TRADE", 0.88, 0.9, "2026-11-13", "2026-12-09"],
    ["KXFEDDECISION-26DEC-H26", "BUY YES", 0.1, 0.07, "2026-11-13", "2026-12-09"],
    ["KXRECSSNBER-26", "NO TRADE", 0.01, 0.03, "2026-11-13", "2027-01-31"],
    ["KXAAAGASMAX-26DEC31-4.60", "BUY NO", 0.04, 0.12, "2026-11-13", "2026-12-31"],
    ["KXAAAGASMAX-26DEC31-4.80", "BUY NO", 0.03, 0.11, "2026-11-13", "2026-12-31"],
    ["KXHORMUZNORM-26MAR17-B271101", "BUY NO", 0.37, 0.51, "2026-11-13", "2027-11-01"],
    ["KXHORMUZNORM-26MAR17-B271001", "BUY NO", 0.35, 0.49, "2026-11-13", "2027-10-01"],
    ["KXHORMUZNORM-26MAR17-B280101", "BUY NO", 0.39, 0.56, "2026-11-13", "2028-01-01"],
    ["KXUSAIRANAGREEMENT-27-29JAN20", "NO TRADE", 0.45, 0.44, "2026-11-13", "2029-01-20"],
    ["KXUSAIRANAGREEMENT-27-28", "NO TRADE", 0.29, 0.3, "2026-11-13", "2028-01-01"],
    ["KXSAVEACT-27-JAN04", "NO TRADE", 0.01, 0.01, "2026-11-13", "2027-01-04"],
    ["KXTRUMPADMINLEAVE-26DEC31-HLUT", "BUY NO", 0.45, 0.65, "2026-11-13", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-AGLE", "NO TRADE", 0.19, 0.18, "2026-11-13", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-PHEG", "BUY YES", 0.18, 0.15, "2026-11-13", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-WSCH", "NO TRADE", 0.1, 0.1, "2026-11-13", "2027-01-01"],
    ["KXNEXTPRESSECPERM-29JAN20-BFER", "BUY NO", 0.2, 0.22, "2026-11-13", "2029-01-20"],
    ["KXNEXTPRESSECPERM-29JAN20-SJEN", "BUY NO", 0.09, 0.13, "2026-11-13", "2029-01-20"],
    ["KXCRYPTOSTRUCTURE-27JAN-28", "BUY NO", 0.14, 0.28, "2026-11-13", "2028-01-01"],
    ["KXOSCARPIC-27-ODY", "NO TRADE", 0.54, 0.53, "2026-11-13", "2027-03-15"],
    ["KXOSCARPIC-27-YOU", "BUY NO", 0.09, 0.23, "2026-11-13", "2027-03-15"],
    ["GTA6-26DEC31", "NO TRADE", 0.99, 0.99, "2026-11-13", "2026-12-31"],
    ["KXGAMEAWARDS-2026-GTA", "BUY NO", 0.75, 0.85, "2026-11-13", "2026-12-15"],
    ["KXDANCINGWITHTHESTARS-26DEC31-EFRE", "BUY NO", 0.52, 0.6, "2026-11-13", "2026-11-24"],
    ["KXDANCINGWITHTHESTARS-26DEC31-HSHU", "NO TRADE", 0.14, 0.13, "2026-11-13", "2026-11-24"],
    ["KXBOND-30-ROB", "BUY NO", 0.48, 0.55, "2026-11-13", "2030-01-01"],
    ["KXBOND-30-CAL", "BUY NO", 0.22, 0.37, "2026-11-13", "2030-01-01"],
    ["KXBOND-30-JAC", "BUY NO", 0.14, 0.27, "2026-11-13", "2030-01-01"],
    ["KXTIME-26-ZOH", "NO TRADE", 0.23, 0.25, "2026-11-13", "2026-12-31"],
    ["KXTIME-26-JAM", "NO TRADE", 0.19, 0.2, "2026-11-13", "2026-12-31"],
    ["KXEARTHQUAKECALIFORNIA-27", "NO TRADE", 0.01, 0.03, "2026-11-13", "2027-01-01"],
    ["KXGTEMP-26-P0", "NO TRADE", 0.91, 0.93, "2026-11-13", "2027-01-01"],
    ["KXHURCTOTMAJ-26DEC01-T1", "NO TRADE", 0.01, 0.02, "2026-11-13", "2026-12-01"],
    ["KXSB-27-SF", "BUY NO", 0.14, 0.16, "2026-11-16", "2027-02-14"],
    ["KXSB-27-BUF", "NO TRADE", 0.14, 0.15, "2026-11-16", "2027-02-14"],
    ["KXNCAAF-27-UGA", "BUY NO", 0.28, 0.35, "2026-11-16", "2027-01-15"],
    ["KXNCAAF-27-ND", "NO TRADE", 0.16, 0.16, "2026-11-16", "2027-01-15"],
    ["KXNBA-27-SAS", "NO TRADE", 0.21, 0.22, "2026-11-16", "2027-06-30"],
    ["KXNBA-27-OKC", "NO TRADE", 0.14, 0.13, "2026-11-16", "2027-06-30"],
    ["KXNFLMVP-27-JBUR", "BUY NO", 0.45, 0.5, "2026-11-16", "2027-02-12"],
    ["KXNFLMVP-27-BPUR", "NO TRADE", 0.16, 0.16, "2026-11-16", "2027-02-12"],
    ["KXNFLMVP-27-JALL", "NO TRADE", 0.18, 0.16, "2026-11-16", "2027-02-12"],
    ["KXHEISMAN-27-JSMIT", "BUY NO", 0.52, 0.57, "2026-11-16", "2026-12-12"],
    ["KXHEISMAN-27-DMENS", "BUY NO", 0.2, 0.27, "2026-11-16", "2026-12-12"],
    ["KXHEISMAN-27-CCARR", "BUY YES", 0.09, 0.05, "2026-11-16", "2026-12-12"],
    ["KXCITRINI-28JUL01", "BUY NO", 0.09, 0.15, "2026-11-16", "2028-07-01"],
    ["KXRATECUTCOUNT-26DEC31-T0", "NO TRADE", 0.99, 0.99, "2026-11-16", "2026-12-31"],
    ["KXFEDDECISION-26DEC-H25", "NO TRADE", 0.87, 0.89, "2026-11-16", "2026-12-09"],
    ["KXFEDDECISION-26DEC-H26", "BUY YES", 0.12, 0.09, "2026-11-16", "2026-12-09"],
    ["KXRECSSNBER-26", "NO TRADE", 0.01, 0.03, "2026-11-16", "2027-01-31"],
    ["KXFEDFUNDSYEAR-28JAN01-T4.25", "BUY YES", 0.49, 0.43, "2026-11-16", "2027-12-31"],
    ["KXFEDFUNDSYEAR-28JAN01-T4.50", "BUY NO", 0.34, 0.4, "2026-11-16", "2027-12-31"],
    ["KXAAAGASMAX-26DEC31-4.60", "BUY NO", 0.03, 0.11, "2026-11-16", "2026-12-31"],
    ["KXAAAGASMAX-26DEC31-4.80", "BUY NO", 0.02, 0.1, "2026-11-16", "2026-12-31"],
    ["KXHORMUZNORM-26MAR17-B270901", "BUY NO", 0.33, 0.45, "2026-11-16", "2027-09-01"],
    ["KXHORMUZNORM-26MAR17-B271001", "BUY NO", 0.35, 0.5, "2026-11-16", "2027-10-01"],
    ["KXHORMUZNORM-26MAR17-B271101", "BUY NO", 0.37, 0.51, "2026-11-16", "2027-11-01"],
    ["KXHORMUZNORM-26MAR17-B280101", "BUY NO", 0.39, 0.55, "2026-11-16", "2028-01-01"],
    ["KXUSAIRANAGREEMENT-27-29JAN20", "NO TRADE", 0.37, 0.35, "2026-11-16", "2029-01-20"],
    ["KXUSAIRANAGREEMENT-27-28", "NO TRADE", 0.27, 0.28, "2026-11-16", "2028-01-01"],
    ["KXSAVEACT-27-JAN04", "NO TRADE", 0.01, 0.01, "2026-11-16", "2027-01-04"],
    ["KXTRUMPADMINLEAVE-26DEC31-HLUT", "BUY NO", 0.34, 0.36, "2026-11-16", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-KHAS", "NO TRADE", 0.3, 0.32, "2026-11-16", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-PHEG", "BUY YES", 0.17, 0.15, "2026-11-16", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-AGLE", "NO TRADE", 0.13, 0.11, "2026-11-16", "2027-01-01"],
    ["KXNEXTPRESSECPERM-29JAN20-BFER", "NO TRADE", 0.2, 0.2, "2026-11-16", "2029-01-20"],
    ["KXNEXTPRESSECPERM-29JAN20-AKEL", "NO TRADE", 0.1, 0.09, "2026-11-16", "2029-01-20"],
    ["KXNEXTPRESSECPERM-29JAN20-SJEN", "NO TRADE", 0.07, 0.08, "2026-11-16", "2029-01-20"],
    ["KXCRYPTOSTRUCTURE-27JAN-28", "BUY NO", 0.14, 0.29, "2026-11-16", "2028-01-01"],
    ["KXOSCARPIC-27-ODY", "NO TRADE", 0.52, 0.51, "2026-11-16", "2027-03-15"],
    ["KXOSCARPIC-27-YOU", "BUY NO", 0.07, 0.23, "2026-11-16", "2027-03-15"],
    ["KXGTA6-26NOV30", "NO TRADE", 0.99, 0.99, "2026-11-16", "2026-11-30"],
    ["KXGAMEAWARDS-2026-GTA", "BUY NO", 0.75, 0.81, "2026-11-16", "2026-12-15"],
    ["KXDANCINGWITHTHESTARS-26DEC31-EFRE", "BUY NO", 0.52, 0.58, "2026-11-16", "2026-11-24"],
    ["KXDANCINGWITHTHESTARS-26DEC31-CWOO", "NO TRADE", 0.2, 0.22, "2026-11-16", "2026-11-24"],
    ["KXDANCINGWITHTHESTARS-26DEC31-HSHU", "NO TRADE", 0.12, 0.1, "2026-11-16", "2026-11-24"],
    ["KXBOND-30-ROB", "BUY NO", 0.57, 0.69, "2026-11-16", "2030-01-01"],
    ["KXBOND-30-CAL", "BUY NO", 0.14, 0.28, "2026-11-16", "2030-01-01"],
    ["KXBOND-30-JAC", "BUY NO", 0.08, 0.12, "2026-11-16", "2030-01-01"],
    ["KXTIME-26-ZOH", "BUY NO", 0.23, 0.26, "2026-11-16", "2026-12-31"],
    ["KXTIME-26-JAM", "NO TRADE", 0.19, 0.2, "2026-11-16", "2026-12-31"],
    ["KXEARTHQUAKECALIFORNIA-27", "NO TRADE", 0.01, 0.02, "2026-11-16", "2027-01-01"],
    ["KXGTEMP-26-P0", "NO TRADE", 0.89, 0.88, "2026-11-16", "2027-01-01"],
    ["KXHURRICANENAMES-26DEC01ATL-FAY", "NO TRADE", 0.01, 0.02, "2026-11-16", "2026-12-01"],
    ["KXHURRICANENAMES-26DEC01ATL-KYL", "NO TRADE", 0.01, 0.02, "2026-11-16", "2026-12-01"],
    ["KXSB-27-SF", "NO TRADE", 0.14, 0.15, "2026-11-18", "2027-02-14"],
    ["KXSB-27-BUF", "NO TRADE", 0.14, 0.14, "2026-11-18", "2027-02-14"],
    ["KXNCAAF-27-UGA", "BUY NO", 0.28, 0.32, "2026-11-18", "2027-01-15"],
    ["KXNCAAF-27-ND", "NO TRADE", 0.16, 0.16, "2026-11-18", "2027-01-15"],
    ["KXNBA-27-SAS", "NO TRADE", 0.21, 0.21, "2026-11-18", "2027-06-30"],
    ["KXNBA-27-OKC", "NO TRADE", 0.14, 0.13, "2026-11-18", "2027-06-30"],
    ["KXNFLMVP-27-JBUR", "BUY NO", 0.45, 0.47, "2026-11-18", "2027-02-12"],
    ["KXNFLMVP-27-JALL", "NO TRADE", 0.18, 0.17, "2026-11-18", "2027-02-12"],
    ["KXHEISMAN-27-JSMIT", "BUY NO", 0.52, 0.59, "2026-11-18", "2026-12-12"],
    ["KXHEISMAN-27-DMENS", "NO TRADE", 0.19, 0.17, "2026-11-18", "2026-12-12"],
    ["KXHEISMAN-27-CCARR", "BUY YES", 0.08, 0.05, "2026-11-18", "2026-12-12"],
    ["KXCITRINI-28JUL01", "BUY NO", 0.09, 0.15, "2026-11-18", "2028-07-01"],
    ["KXRATECUTCOUNT-26DEC31-T0", "NO TRADE", 0.99, 0.99, "2026-11-18", "2026-12-31"],
    ["KXFEDDECISION-26DEC-H25", "NO TRADE", 0.94, 0.93, "2026-11-18", "2026-12-09"],
    ["KXFEDDECISION-26DEC-H26", "NO TRADE", 0.05, 0.06, "2026-11-18", "2026-12-09"],
    ["KXFEDFUNDSYEAR-28JAN01-T4.25", "BUY YES", 0.48, 0.4, "2026-11-18", "2027-12-31"],
    ["KXFEDFUNDSYEAR-28JAN01-T4.50", "NO TRADE", 0.33, 0.33, "2026-11-18", "2027-12-31"],
    ["KXAAAGASMAX-26DEC31-4.60", "BUY NO", 0.02, 0.06, "2026-11-18", "2026-12-31"],
    ["KXAAAGASMAX-26DEC31-4.80", "BUY NO", 0.01, 0.05, "2026-11-18", "2026-12-31"],
    ["KXHORMUZNORM-26MAR17-B270901", "NO TRADE", 0.28, 0.29, "2026-11-18", "2027-09-01"],
    ["KXHORMUZNORM-26MAR17-B271001", "BUY NO", 0.31, 0.39, "2026-11-18", "2027-10-01"],
    ["KXHORMUZNORM-26MAR17-B271101", "BUY NO", 0.33, 0.41, "2026-11-18", "2027-11-01"],
    ["KXHORMUZNORM-26MAR17-B271201", "BUY NO", 0.35, 0.46, "2026-11-18", "2027-12-01"],
    ["KXHORMUZNORM-26MAR17-B280101", "BUY NO", 0.37, 0.53, "2026-11-18", "2028-01-01"],
    ["KXUSAIRANAGREEMENT-27-29JAN20", "NO TRADE", 0.36, 0.36, "2026-11-18", "2029-01-20"],
    ["KXUSAIRANAGREEMENT-27-28", "NO TRADE", 0.27, 0.29, "2026-11-18", "2028-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-MBAU", "NO TRADE", 0.62, 0.64, "2026-11-18", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-KHAS", "NO TRADE", 0.3, 0.3, "2026-11-18", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-HLUT", "NO TRADE", 0.24, 0.23, "2026-11-18", "2027-01-01"],
    ["KXTRUMPADMINLEAVE-26DEC31-PHEG", "BUY YES", 0.16, 0.14, "2026-11-18", "2027-01-01"],
    ["KXNEXTPRESSECPERM-29JAN20-BFER", "NO TRADE", 0.18, 0.16, "2026-11-18", "2029-01-20"],
    ["KXNEXTPRESSECPERM-29JAN20-AKEL", "NO TRADE", 0.1, 0.1, "2026-11-18", "2029-01-20"],
    ["KXCRYPTOSTRUCTURE-27JAN-28", "BUY NO", 0.14, 0.23, "2026-11-18", "2028-01-01"],
    ["KXCRYPTOSTRUCTURE-27JAN-27OCT01", "BUY NO", 0.11, 0.19, "2026-11-18", "2027-10-01"],
    ["KXOSCARPIC-27-ODY", "NO TRADE", 0.52, 0.53, "2026-11-18", "2027-03-15"],
    ["KXOSCARPIC-27-YOU", "BUY NO", 0.07, 0.2, "2026-11-18", "2027-03-15"],
    ["KXGTA6-26NOV30", "NO TRADE", 0.99, 0.99, "2026-11-18", "2026-11-30"],
    ["KXGAMEAWARDS-2026-GTA", "BUY NO", 0.92, 0.95, "2026-11-18", "2026-12-15"],
    ["KXDANCINGWITHTHESTARS-26DEC31-EFRE", "BUY NO", 0.52, 0.54, "2026-11-18", "2026-11-24"],
    ["KXDANCINGWITHTHESTARS-26DEC31-AGLE", "NO TRADE", 0.24, 0.22, "2026-11-18", "2026-11-24"],
    ["KXFEATURE-26GTA6-21S", "NO TRADE", 0.02, 0.04, "2026-11-18", "2026-12-31"],
    ["KXFEATURE-26GTA6-BAD", "NO TRADE", 0.02, 0.04, "2026-11-18", "2026-12-31"],
    ["KXTIME-26-ZOH", "BUY NO", 0.23, 0.26, "2026-11-18", "2026-12-31"],
    ["KXTIME-26-JAM", "BUY NO", 0.19, 0.22, "2026-11-18", "2026-12-31"],
    ["KXGTEMP-26-P0", "NO TRADE", 0.89, 0.88, "2026-11-18", "2027-01-01"],
    ["KXEARTHQUAKECALIFORNIA-27", "NO TRADE", 0.01, 0.02, "2026-11-18", "2027-01-01"],
    ["KXHURRICANENAMES-26DEC01ATL-KYL", "BUY NO", 0.04, 0.1, "2026-11-18", "2026-12-01"],
    ["KXHURRICANENAMES-26DEC01ATL-FAY", "NO TRADE", 0.01, 0.01, "2026-11-18", "2026-12-01"],
    ["KXHURCTOTMAJ-26DEC01-T1", "NO TRADE", 0.01, 0.02, "2026-11-18", "2026-12-01"]
]


def main(db_path=DB_PATH, apply=False):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""SELECT id, ticker, recommendation, afg_probability, kalshi_price, outcome, close_date
                   FROM predictions
                   WHERE (published_date IS NULL OR TRIM(published_date) = '')
                   AND status NOT IN ('Void','Superseded') ORDER BY id""")
    rows = cur.fetchall()
    if not rows:
        print("No active rows are missing a published_date. Nothing to do.")
        return 0
    print(f"{len(rows)} active row(s) have no published_date:\n")
    changes, unmatched = [], []
    for rid, t, rec, afg, kal, outcome, close in rows:
        try:
            key = (t, rec, round(float(afg), 2), round(float(kal), 2))
        except (TypeError, ValueError):
            unmatched.append((rid, t, rec, afg, kal, "probability not numeric"))
            continue
        hits = [c for c in PUBLISHED if (c[0], c[1], c[2], c[3]) == key]
        dates = sorted({c[4] for c in hits})
        if len(dates) != 1:
            unmatched.append((rid, t, rec, afg, kal,
                              "no matching published call" if not dates else f"matches several dates {dates}"))
            continue
        new_close = close if close not in (None, "") else hits[0][5]
        changes.append((dates[0], new_close, rid))
        print(f"  id={rid:<5} {t:<38} {rec:<8} {afg} vs {kal}  outcome={outcome}  "
              f"published_date None -> {dates[0]}   close_date {close} -> {new_close}")
    for u in unmatched:
        print(f"  id={u[0]:<5} {u[1]:<38} {u[2]:<8} {u[3]} vs {u[4]}  LEFT UNCHANGED: {u[5]}")

    if unmatched:
        print("\nSome rows could not be matched to a published call. Send this output to Claude"
              " before applying; nothing has been changed.")
        return 1
    if not apply:
        print(f"\nPREVIEW: {len(changes)} row(s) would change. Run with --apply to make the change.")
        return 0
    cur.executemany("UPDATE predictions SET published_date=?, close_date=? WHERE id=?", changes)
    conn.commit()
    conn.close()
    print(f"\nUpdated {len(changes)} row(s). Run diag_accuracy_match.py: both methods should now agree."
          "\nThen run run_cycle.py again.")
    return 0


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))
