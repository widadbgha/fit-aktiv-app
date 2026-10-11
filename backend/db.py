"""
Datenbank-Zugriff (Datenhaltungsschicht).

Kapselt die Verbindung zur SQLite-Datei. Entspricht der
Datenhaltungsschicht des 3-Schichten-Modells (Kapitel 4 des
Projektberichts). Zugriff ausschliesslich ueber das sqlite3-Modul.
"""

import os
import sqlite3
from flask import g

# Pfad zur Datenbank-Datei (eine einzelne Datei, serverlos)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "fit_aktiv.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# Version des Datenbestands. Wird bei jeder Aenderung von Schema ODER
# Seed-Daten erhoeht; die App erkennt eine veraltete Datenbank daran und
# baut sie beim Start automatisch neu auf.
SEED_VERSION = 2


def get_db():
    """Liefert die (pro Request zwischengespeicherte) DB-Verbindung."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row          # Zugriff per Spaltenname
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exc=None):
    """Schliesst die Verbindung am Ende des Requests."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    """Hilfsfunktion fuer SELECT-Abfragen."""
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    """Hilfsfunktion fuer INSERT/UPDATE/DELETE; gibt lastrowid zurueck."""
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    last = cur.lastrowid
    cur.close()
    return last


def init_db():
    """Legt das Schema neu an (entfernt eine evtl. vorhandene DB-Datei)."""
    # Vorhandene (ggf. unvollstaendige/defekte) Datei entfernen, damit das
    # Schema garantiert frisch erzeugt werden kann.
    for pfad in (DB_PATH, DB_PATH + "-journal"):
        try:
            if os.path.exists(pfad):
                os.remove(pfad)
        except OSError:
            pass
    con = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()
    con.close()


def db_exists():
    return os.path.exists(DB_PATH)
