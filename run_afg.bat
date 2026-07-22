@echo off
REM run_afg.bat -- runs the full setup + Phase 1 test in one shot.
REM Double-click this file in File Explorer, or type its name once in cmd.
REM No copy-pasting of multiple commands required.

cd /d C:\Users\qwhit\AFG

echo ============================================
echo STEP 1: Setting up the database
echo ============================================
python3 db.py

echo.
echo ============================================
echo STEP 2: Running Phase 1 (market pull) -- this is the real test
echo ============================================
python3 01_pull_markets.py

echo.
echo ============================================
echo STEP 3: Running Phase 5 (scorecard update)
echo ============================================
python3 05_update_scorecard.py

echo.
echo ============================================
echo DONE. Scroll up to see the output of each step.
echo ============================================
pause
