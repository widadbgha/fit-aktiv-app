# Fit & Aktiv – Kurs- und Trainerverwaltung
> **English summary:** Fit & Aktiv is a web application for scheduling fitness courses and managing trainers across 15 studios. Built with **Python (Flask)** and **SQLite** in a 3-layer architecture, it generates weekly course plans automatically (weekly hour limits, travel-time buffers between studios, room allocation), finds substitute trainers when someone reports sick, and provides role-based access for owner, studio managers and trainers. Developed as a university project (Software Engineering, SS 2026) , including requirements analysis, design documentation and automated tests.

Implementierung zum Projektbericht der Projektgruppe 23-E (SWE-Praktikum, SS 2026).
Die Anwendung setzt das in den Kapiteln 4–8 beschriebene Design 1:1 um:
Web-Applikation mit **Flask (Python)**, **SQLite**-Datenbank und einem
**3-Schichten-Modell** (Browser-Frontend → Flask-Server → SQLite).

---

## Schnellstart

### Variante A – Startskript (am einfachsten)
- **macOS:** Datei `run.command` doppelklicken (oder im Terminal `./run.command`).
- **Windows:** Datei `run.bat` doppelklicken.

Das Skript legt eine virtuelle Umgebung an, installiert Flask, erzeugt beim
ersten Start die Demo-Datenbank und startet den Server.

### Variante B – manuell (Python ist installiert)
```bash
cd fit-aktiv-app
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python backend/seed.py                   # Demo-Datenbank anlegen (einmalig)
python backend/app.py                    # Server starten
```

Anschließend im Browser öffnen: **http://127.0.0.1:5000**

### Demo-Zugänge (Passwort jeweils `demo1234`)
| Rolle           | Benutzername | Sieht / kann |
|-----------------|--------------|--------------|
| Chef            | `chef`       | alles (Verwaltung, Pläne aller Studios, Krankmeldung) |
| Studio-Manager  | `manager1`   | nur eigenes Studio (Plan, Krankmeldung) |
| Trainer         | `trainer1`   | nur eigenen Wochenplan + Selbst-Krankmeldung |

(Angelegt sind `manager1`–`manager15` und `trainer1`–`trainer60`.)

Datenbestand der finalen Version: **15 Studios** (Region Krefeld) mit je 3 Räumen,
**60 Trainer** (Voll-/Teilzeit, je 2 Studios zugeordnet), **15 Studio-Manager**
(einer je Studio) und der Chef. Die übrigen ~25 Mitarbeiter der ~100-köpfigen
Belegschaft (Reinigung/Verwaltung) sind laut Rollenmodell nicht systemrelevant.

---

## Umsetzung der Anforderungen

| Anforderung | Umsetzung |
|-------------|-----------|
| **FA-01** rollenbasierte Anmeldung | `login`, Sessions, Rollen Chef/Manager/Trainer |
| **FA-02** Trainer verwalten (K)    | `/verwaltung/trainer` (anlegen, bearbeiten, löschen, Studio-Zuordnung) |
| **FA-03** Studios verwalten (S)    | `/verwaltung/studios` |
| **FA-04** Kurstypen verwalten (S)  | `/verwaltung/kurse` |
| **FA-05** Wochenplan automatisch   | `domain.generiere_wochenplan` (Button „Plan generieren“) |
| **FA-06** Wochenstundenlimit       | VZ 20 / TZ 10 – `limit_erreicht` |
| **FA-07** Fahrzeitpuffer           | 120 Min Startabstand bei Studiowechsel – `verletzt_fahrzeitpuffer` |
| **FA-08** Trainer verteilen        | Auswahl des am wenigsten ausgelasteten Trainers |
| **FA-09** Vertretungssuche         | `finde_ersatztrainer` (alle Bedingungen) |
| **FA-10** Kursausfall + Hinweis    | Markierung `ausgefallen`, Warnmeldung „zusätzliche Mitarbeiter einstellen“ |
| **FA-12** Manager nur eigenes Studio (K) | Rollenprüfung, gefilterte Ansichten |
| **FA-13** Trainer nur eigener Plan | `/mein-plan`, kein Zugriff auf andere Bereiche |
| **FA-14** Farbcodierung            | blau = normal, orange = Vertretung, rot = ausgefallen |
| **FA-15** Dashboard-Kennzahlen     | `/` (Trainer-/Studio-/Kurs-Anzahl, offene Krankmeldungen, Ausfälle) |
| **FA-16** Filter Studio/KW         | Auswahl im Wochenplan |
| **NFA-01** Web-App im Browser      | Flask + HTML/CSS/JS, getestet in Chrome/Firefox/Edge |
| **NFA-02** Persistenz              | alle Änderungen in SQLite |
| **NFA-04** lokaler Server          | `python backend/app.py` |
| **NFA-05** strukturierter Code     | Schichten getrennt: `db.py`, `domain.py`, `app.py`, Templates |

**Geschäftsprozesse:** Krankmeldung mit Zeitraum (5.1) → `verarbeite_krankmeldung`;
automatische Wochenplanung (5.2) → `generiere_wochenplan`.

---

## Datenmodell

Die fünf Kerntabellen entsprechen exakt dem ER-Diagramm (Kapitel 6):
`users`, `studios`, `trainer`, `kurse`, `plaene` (mit `uhrzeit` als
Zeitslot-INT 1–6). Zwei technisch notwendige Realisierungen dokumentierter
Inhalte:

- **`trainer_studios`** – Verknüpfungstabelle für die im ER-Diagramm
  dokumentierte N:M-Beziehung „arbeitet in”.
- **`plaene.vertretung`** – Kennzeichen für die in FA-14 geforderte
  farbliche Unterscheidung „Vertretung”.
- **`plaene.raum`** (1–3) – Raum im Studio. Jedes Studio hat 3 Räume;
  parallele Kurse zur selben Zeit belegen verschiedene Räume (ein Raum ist
  nie doppelt belegt). Diese drei Punkte sind App-Erweiterungen gegenüber dem
  dokumentierten 5-Tabellen-Modell.

Zeitslots: 1 = 09:00, 2 = 10:00, 3 = 11:00, 4 = 14:00, 5 = 15:00, 6 = 16:00
(je 60 Minuten). Tage: 1 = Montag … 6 = Samstag.

---

## Projektstruktur

```
fit-aktiv-app/
├── backend/          # Backend (Anwendungs- + Datenhaltungsschicht)
│   ├── app.py        # Flask-Routen / Steuerung
│   ├── domain.py     # Geschäftslogik: Planung + Krankmeldung (Kap. 5)
│   ├── db.py         # Datenbankzugriff
│   ├── schema.sql    # Tabellendefinitionen (Kap. 6)
│   └── seed.py       # Demo-Daten + Beispiel-Wochenplan
├── frontend/         # Frontend (Präsentationsschicht)
│   ├── templates/    # HTML-Seiten (Jinja2)
│   └── static/       # style.css (Layout, Kap. 7)
├── tests/            # Automatische Tests
│   ├── test_app.py
│   └── verify_rules.py
├── requirements.txt
├── run.command / run.bat
└── README.md
```

## Tests
```bash
python backend/seed.py
python tests/test_app.py       # 15 Testfälle (Login, Rollen, Plan, Krankmeldung)
python tests/verify_rules.py   # prüft den generierten Plan auf Regelverstöße
```
