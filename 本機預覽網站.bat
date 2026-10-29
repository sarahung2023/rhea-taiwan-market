@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "" "http://localhost:8765"
  py -3 -m http.server 8765
) else (
  start "" "http://localhost:8765"
  python -m http.server 8765
)
pause
