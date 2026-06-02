@echo off
REM ============================================================
REM  TEA economic-analysis report generator (double-click me)
REM  - regenerates a dossier for every paper
REM  - opens the report index in your default browser
REM ============================================================
cd /d "%~dp0tea_tool"

echo Checking dependencies (first run may take a minute)...
python -m pip install -q -r requirements.txt 2>nul || py -3 -m pip install -q -r requirements.txt

echo.
echo Generating dossiers for all papers...
python generate_dossiers.py 2>nul || py -3 generate_dossiers.py

echo.
echo Opening the report in your browser...
start "" "dossier\index.html"

echo.
echo Done. You can close this window.
pause
