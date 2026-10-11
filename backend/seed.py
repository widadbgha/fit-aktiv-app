"""
Demo-/Echtdaten fuer "Fit & Aktiv" (finale Version).

Legt das Schema neu an und befuellt die Datenbank mit einer realistischen
Belegschaft der Fitnessstudio-Kette:

  * 15 Studios in der Region Krefeld
  * 60 Trainer (Voll-/Teilzeit), je 2 Studios zugeordnet
  * 15 Studio-Manager (genau einer je Studio)
  *  1 Chef (Lisa Fit)

Die uebrigen ~25 Mitarbeiter (Reinigung, Verwaltung, sonstiges Personal)
sind fuer das System nicht relevant und werden daher nicht erfasst
(Gesamtbelegschaft laut Rahmenbedingungen: rund 100 Mitarbeiter).

Aufruf:  python seed.py
"""

import sqlite3
import random
from werkzeug.security import generate_password_hash

import db
import domain

DEMO_PASSWORT = "demo1234"
random.seed(2026)   # reproduzierbare Zuordnung

# 15 Studios (Region Krefeld) -----------------------------------------------
STUDIOS = [
    ("Fit & Aktiv Krefeld-Mitte",  "Hauptstraße 12, 47798 Krefeld"),
    ("Fit & Aktiv Krefeld-Süd",    "Südwall 5, 47800 Krefeld"),
    ("Fit & Aktiv Krefeld-Nord",   "Nordstraße 88, 47802 Krefeld"),
    ("Fit & Aktiv Krefeld-Ost",    "Dießemer Bruch 140, 47805 Krefeld"),
    ("Fit & Aktiv Uerdingen",      "Rheinstraße 30, 47829 Krefeld"),
    ("Fit & Aktiv Fischeln",       "Kölner Straße 210, 47807 Krefeld"),
    ("Fit & Aktiv Hüls",           "Hülser Markt 3, 47839 Krefeld"),
    ("Fit & Aktiv Oppum",          "Oppumer Straße 55, 47809 Krefeld"),
    ("Fit & Aktiv Linn",           "Rheinbabenstraße 9, 47809 Krefeld"),
    ("Fit & Aktiv Bockum",         "Uerdinger Straße 470, 47800 Krefeld"),
    ("Fit & Aktiv Traar",          "Moerser Landstraße 2, 47802 Krefeld"),
    ("Fit & Aktiv Verberg",        "Gartenstadtweg 17, 47802 Krefeld"),
    ("Fit & Aktiv Willich",        "Bahnstraße 40, 47877 Willich"),
    ("Fit & Aktiv Tönisvorst",     "Hauptstraße 75, 47918 Tönisvorst"),
    ("Fit & Aktiv Meerbusch",      "Düsseldorfer Straße 12, 40667 Meerbusch"),
]

KURSE = ["Yoga", "Pilates", "Spinning", "Krafttraining", "Functional Fit"]

VORNAMEN = ["Anna", "Ben", "Carla", "David", "Eva", "Felix", "Greta", "Hassan",
            "Ina", "Jonas", "Klara", "Lukas", "Mara", "Nils", "Olivia", "Paul",
            "Rosa", "Sven", "Tessa", "Umut", "Vera", "Walid", "Xenia", "Yusuf",
            "Zoe", "Aylin", "Bjarne", "Clara", "Dennis", "Elif"]
NACHNAMEN = ["Krause", "Yılmaz", "Möller", "Schäfer", "Petrov", "Stark", "Lang",
             "Boudib", "Zander", "Lauer", "Sommer", "Fischer", "Berg", "Falk",
             "Reuter", "Wagner", "Hoffmann", "Vogel", "Brandt", "Kaya", "Schulz",
             "Becker", "Roth", "Neumann", "Albrecht", "Esposito", "Nowak"]

MANAGER_NAMEN = ["Markus Berg", "Sandra Falk", "Tom Reuter", "Petra Kühn",
                 "Ali Demir", "Nina Wolf", "Jan Kurz", "Lea Horn", "Erik Maas",
                 "Sonja Reif", "Dirk Acker", "Mira Pohl", "Ben Otto",
                 "Hanna Vogt", "Kai Lorenz"]


def eindeutige_namen(anzahl):
    namen, gesehen = [], set()
    while len(namen) < anzahl:
        n = f"{random.choice(VORNAMEN)} {random.choice(NACHNAMEN)}"
        if n not in gesehen:
            gesehen.add(n)
            namen.append(n)
    return namen


def seed():
    db.init_db()
    con = sqlite3.connect(db.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    pw = generate_password_hash(DEMO_PASSWORT)

    # Studios
    studio_ids = []
    for name, adr in STUDIOS:
        cur = con.execute("INSERT INTO studios (name, adresse) VALUES (?,?)", (name, adr))
        studio_ids.append(cur.lastrowid)

    # Kurstypen
    for name in KURSE:
        con.execute("INSERT INTO kurse (name) VALUES (?)", (name,))

    # Chef
    con.execute("INSERT INTO users (username, password, rolle, name) VALUES (?,?,?,?)",
                ("chef", pw, "chef", "Lisa Fit"))

    # 15 Manager – genau einer je Studio
    for i, name in enumerate(MANAGER_NAMEN):
        con.execute(
            "INSERT INTO users (username, password, rolle, name, studioId) VALUES (?,?,?,?,?)",
            (f"manager{i+1}", pw, "manager", name, studio_ids[i]))

    # 60 Trainer – je 2 Studios; jedes Studio erhaelt mindestens 4 Trainer
    trainer_namen = eindeutige_namen(60)
    for i, name in enumerate(trainer_namen, start=1):
        typ = "VZ" if (i % 5) < 3 else "TZ"          # ~60 % Vollzeit
        cur = con.execute("INSERT INTO trainer (name, typ, krank) VALUES (?,?,0)", (name, typ))
        tid = cur.lastrowid
        cur = con.execute(
            "INSERT INTO users (username, password, rolle, name, trainerId) VALUES (?,?,?,?,?)",
            (f"trainer{i}", pw, "trainer", name, tid))
        con.execute("UPDATE trainer SET userId=? WHERE id=?", (cur.lastrowid, tid))
        # Primaerstudio per Round-Robin (garantiert >=4 je Studio) + ein weiteres
        haupt = studio_ids[(i - 1) % len(studio_ids)]
        weiteres = random.choice([s for s in studio_ids if s != haupt])
        for sid in (haupt, weiteres):
            con.execute("INSERT INTO trainer_studios (trainerId, studioId) VALUES (?,?)", (tid, sid))
    con.commit()

    # Wochenplan fuer aktuelle und naechste KW (alle Studios)
    kw = domain.aktuelle_kw()
    r1 = domain.generiere_wochenplan(con, kw, studio_ids, seed=42)
    r2 = domain.generiere_wochenplan(con, kw + 1, studio_ids, seed=43)
    # Version des Datenbestands in der DB hinterlegen
    con.execute(f"PRAGMA user_version = {db.SEED_VERSION}")
    con.commit()
    con.close()

    print(f"Demo-Daten angelegt: {len(STUDIOS)} Studios, 60 Trainer, "
          f"{len(MANAGER_NAMEN)} Manager, 1 Chef.")
    print(f"Wochenplan KW {kw}: {r1['geplant']} Kurse ({r1['parallel']} parallel, "
          f"{r1['ausgefallen']} ausgefallen) | KW {kw+1}: {r2['geplant']} Kurse.")
    print(f"Login: chef / {DEMO_PASSWORT}  |  manager1..15 / {DEMO_PASSWORT}  "
          f"|  trainer1..60 / {DEMO_PASSWORT}")


if __name__ == "__main__":
    seed()
