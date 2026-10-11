-- ============================================================
--  Fit & Aktiv – Kurs- und Trainerverwaltung
--  Datenbankschema (SQLite)
--
--  Setzt das Datenmodell aus Kapitel 6 des Projektberichts um
--  (ER-Diagramm, Abb. 6). Die fuenf Kerntabellen entsprechen
--  exakt der dokumentierten Tabellenstruktur:
--      users, studios, trainer, kurse, plaene
--
--  Zwei technisch notwendige Ergaenzungen (im Bericht als
--  Beziehung bzw. Anforderung beschrieben, hier konkret
--  realisiert):
--   * trainer_studios : Verknuepfungstabelle fuer die im
--     ER-Diagramm dokumentierte N:M-Beziehung "arbeitet in"
--     (ein Trainer kann in mehreren Studios eingeteilt sein).
--   * plaene.vertretung : Kennzeichen fuer FA-14 (farbliche
--     Unterscheidung normal / Vertretung / ausgefallen).
-- ============================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS trainer_studios;
DROP TABLE IF EXISTS plaene;
DROP TABLE IF EXISTS kurse;
DROP TABLE IF EXISTS trainer;
DROP TABLE IF EXISTS studios;
DROP TABLE IF EXISTS users;

-- Benutzer mit Rolle (Chef, Manager, Trainer) -- FA-01
CREATE TABLE users (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT    NOT NULL UNIQUE,
    password  TEXT    NOT NULL,            -- gehashtes Passwort
    rolle     TEXT    NOT NULL CHECK (rolle IN ('chef','manager','trainer')),
    name      TEXT    NOT NULL,
    trainerId INTEGER REFERENCES trainer(id),  -- nur bei Rolle 'trainer'
    studioId  INTEGER REFERENCES studios(id)   -- nur bei Rolle 'manager'
);

-- Standorte / Studios
CREATE TABLE studios (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    adresse TEXT
);

-- Trainer (Vollzeit VZ / Teilzeit TZ), krank als Status-Flag (0/1)
CREATE TABLE trainer (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    userId INTEGER REFERENCES users(id),
    name   TEXT NOT NULL,
    typ    TEXT NOT NULL CHECK (typ IN ('VZ','TZ')),
    krank  INTEGER NOT NULL DEFAULT 0 CHECK (krank IN (0,1))
);

-- Kurstypen (z. B. Yoga, Pilates ...)
CREATE TABLE kurse (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

-- Konkrete Kurstermine ("Wann, wo, welcher Kurs, welcher Trainer")
--   uhrzeit : INTEGER-Zeitslot (1 = erste Stunde, 2 = zweite Stunde ...)
--   tag     : 1 = Montag ... 6 = Samstag
--   woche   : Kalenderwoche (KW)
--   raum    : Raum-Nummer im Studio (1-3). Jedes Studio hat 3 Raeume;
--             parallele Kurse zur selben Zeit belegen verschiedene Raeume.
CREATE TABLE plaene (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    woche      INTEGER NOT NULL,
    tag        INTEGER NOT NULL CHECK (tag BETWEEN 1 AND 6),
    uhrzeit    INTEGER NOT NULL CHECK (uhrzeit BETWEEN 1 AND 6),
    raum       INTEGER NOT NULL DEFAULT 1 CHECK (raum BETWEEN 1 AND 3),
    trainerId  INTEGER REFERENCES trainer(id),
    studioId   INTEGER NOT NULL REFERENCES studios(id),
    kursId     INTEGER NOT NULL REFERENCES kurse(id),
    ausgefallen INTEGER NOT NULL DEFAULT 0 CHECK (ausgefallen IN (0,1)),
    vertretung  INTEGER NOT NULL DEFAULT 0 CHECK (vertretung IN (0,1))
);

-- N:M-Beziehung "arbeitet in": Trainer <-> Studios
CREATE TABLE trainer_studios (
    trainerId INTEGER NOT NULL REFERENCES trainer(id),
    studioId  INTEGER NOT NULL REFERENCES studios(id),
    PRIMARY KEY (trainerId, studioId)
);
