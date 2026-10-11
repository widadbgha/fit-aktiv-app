@echo off
REM Startskript fuer Windows - einfach doppelklicken.
cd /d "%~dp0"

echo == Fit ^& Aktiv - Kurs- und Trainerverwaltung ==

where python >nul 2>nul
if errorlevel 1 (
  echo Python ist nicht installiert. Bitte von python.org installieren ^(Haken "Add to PATH" setzen^).
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Erstelle virtuelle Umgebung ...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Installiere Abhaengigkeiten ...
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo.
echo Server startet auf http://127.0.0.1:5000  (zum Beenden: Strg+C)
echo Login: chef / demo1234
echo.
python backend\app.py
