@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\update.py
) else (
  python scripts\update.py
)
if errorlevel 1 (
  echo.
  echo ERROR - Official feed failed. Previous verified report is preserved.
) else (
  echo.
  echo SUCCESS - Open http://localhost:8765 with local preview server.
)
pause
