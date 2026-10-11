#!/bin/bash
# Startskript fuer macOS – einfach doppelklicken (oder im Terminal ausfuehren).
cd "$(dirname "$0")" || exit 1

echo "== Fit & Aktiv – Kurs- und Trainerverwaltung =="

# Python finden
PY=python3
command -v $PY >/dev/null 2>&1 || PY=python
command -v $PY >/dev/null 2>&1 || { echo "Python ist nicht installiert. Bitte von python.org installieren."; read -r; exit 1; }

# Virtuelle Umgebung anlegen / aktivieren
if [ ! -d ".venv" ]; then
  echo "Erstelle virtuelle Umgebung ..."
  $PY -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installiere Abhaengigkeiten ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "Server startet auf http://127.0.0.1:5000  (zum Beenden: Strg+C)"
echo "Login: chef / demo1234"
echo ""
# Startet den Server; die Datenbank wird beim ersten Start automatisch
# angelegt (siehe backend/app.py -> _datenbank_ok / seed).
python backend/app.py
