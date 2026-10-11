"""
Geschaeftslogik (Anwendungsschicht).

Enthaelt die Domaenenkonstanten und die zentralen Algorithmen aus
Kapitel 5 des Projektberichts:

  * generiere_wochenplan(...)      -> Geschaeftsprozess 5.2
  * verarbeite_krankmeldung(...)   -> Geschaeftsprozess 5.1

Alle Planungsregeln (FA-06 Wochenstundenlimit, FA-07 Fahrzeitpuffer,
keine Doppelbelegung, parallele Kurse im selben Studio erlaubt) sind
hier zentral umgesetzt. Die Funktionen erhalten eine offene
sqlite3-Verbindung `con`, damit sie sowohl im Web-Request als auch
beim Seeding verwendet werden koennen.
"""

import random
from datetime import date, timedelta

# ---- Domaenenkonstanten -------------------------------------------------

# Wochentage 1..6 (Sonntag ist Ruhetag und wird nicht verplant)
TAGE = {1: "Montag", 2: "Dienstag", 3: "Mittwoch",
        4: "Donnerstag", 5: "Freitag", 6: "Samstag"}
TAGE_KURZ = {1: "Mo", 2: "Di", 3: "Mi", 4: "Do", 5: "Fr", 6: "Sa"}

# Zeitslots: uhrzeit wird als INT gespeichert (1 = erste Stunde ...).
# Jeder Kurs dauert einheitlich 60 Minuten.
SLOTS = {1: "09:00", 2: "10:00", 3: "11:00",
         4: "14:00", 5: "15:00", 6: "16:00"}
# Startzeit jedes Slots in Minuten ab Mitternacht (fuer den Fahrzeitpuffer)
SLOT_START_MIN = {1: 9 * 60, 2: 10 * 60, 3: 11 * 60,
                  4: 14 * 60, 5: 15 * 60, 6: 16 * 60}

KURSDAUER_MIN = 60            # Kursdauer
FAHRZEIT_MIN = 60             # reine Fahrzeit zwischen zwei Studios (FA-07: "1 Stunde")
# Mindestabstand zwischen den STARTZEITEN zweier Kurse desselben Trainers
# in VERSCHIEDENEN Studios = Kursdauer + Fahrzeit = 60 + 60 = 120 Minuten
# (Beispiel: Kurs 09:00-10:00 in Studio A -> naechster Kurs in Studio B
#  fruehestens 11:00; 09:00 -> 11:00 = 120 Minuten Abstand).
MIN_STARTABSTAND_STUDIOWECHSEL = KURSDAUER_MIN + FAHRZEIT_MIN   # 120

# Wochenstundenlimit pro Trainertyp (FA-06): Anzahl Kurse pro Woche
WOCHENLIMIT = {"VZ": 20, "TZ": 10}

# Wahrscheinlichkeit, dass in einem Zeitslot ein zweiter, paralleler Kurs im
# selben Studio angelegt wird. Laut Datenmodell sind parallele Kurse im selben
# Studio ausdruecklich erlaubt (mehrere Raeume / Trainingsbereiche).
PARALLEL_WAHRSCHEINLICHKEIT = 0.45


# ---- Pruef-Hilfsfunktionen ----------------------------------------------

def trainer_in_studio(con, trainer_id, studio_id):
    """Ist der Trainer dem Studio zugeordnet? (N:M 'arbeitet in')"""
    row = con.execute(
        "SELECT 1 FROM trainer_studios WHERE trainerId=? AND studioId=?",
        (trainer_id, studio_id)).fetchone()
    return row is not None


def hat_doppelbelegung(con, trainer_id, woche, tag, uhrzeit):
    """Hat der Trainer zur selben Zeit bereits einen (aktiven) Kurs?"""
    row = con.execute(
        """SELECT 1 FROM plaene
           WHERE trainerId=? AND woche=? AND tag=? AND uhrzeit=?
             AND ausgefallen=0""",
        (trainer_id, woche, tag, uhrzeit)).fetchone()
    return row is not None


def verletzt_fahrzeitpuffer(con, trainer_id, woche, tag, uhrzeit, studio_id):
    """
    Pruefen, ob ein Einsatz im (studio_id, tag, uhrzeit) den Fahrzeitpuffer
    verletzt: zwischen den Startzeiten zweier Kurse in VERSCHIEDENEN Studios
    muessen mind. 120 Minuten liegen. Kurse im selben Studio duerfen direkt
    aufeinanderfolgen (kein Fahrweg) und auch parallel stattfinden.
    """
    start_neu = SLOT_START_MIN[uhrzeit]
    rows = con.execute(
        """SELECT uhrzeit, studioId FROM plaene
           WHERE trainerId=? AND woche=? AND tag=? AND ausgefallen=0""",
        (trainer_id, woche, tag)).fetchall()
    for r in rows:
        if r["studioId"] == studio_id:
            continue  # gleiches Studio -> kein Fahrweg noetig
        abstand = abs(SLOT_START_MIN[r["uhrzeit"]] - start_neu)
        if abstand < MIN_STARTABSTAND_STUDIOWECHSEL:
            return True
    return False


def wochenstunden(con, trainer_id, woche):
    """Anzahl der (aktiven) Kurse des Trainers in der Woche."""
    row = con.execute(
        """SELECT COUNT(*) AS n FROM plaene
           WHERE trainerId=? AND woche=? AND ausgefallen=0""",
        (trainer_id, woche)).fetchone()
    return row["n"]


def limit_erreicht(con, trainer_row, woche):
    """Ist das Wochenstundenlimit des Trainers bereits ausgeschoepft?"""
    grenze = WOCHENLIMIT[trainer_row["typ"]]
    return wochenstunden(con, trainer_row["id"], woche) >= grenze


def trainer_verfuegbar(con, trainer_row, woche, tag, uhrzeit, studio_id):
    """Alle Bedingungen fuer einen Einsatz pruefen (FA-06/07/09)."""
    if trainer_row["krank"]:
        return False
    if not trainer_in_studio(con, trainer_row["id"], studio_id):
        return False
    if hat_doppelbelegung(con, trainer_row["id"], woche, tag, uhrzeit):
        return False
    if verletzt_fahrzeitpuffer(con, trainer_row["id"], woche, tag, uhrzeit, studio_id):
        return False
    if limit_erreicht(con, trainer_row, woche):
        return False
    return True


def finde_ersatztrainer(con, woche, tag, uhrzeit, studio_id, ausser_trainer_id):
    """
    Sucht einen verfuegbaren Ersatztrainer fuer einen Kurs (FA-09).
    Auswahl des am wenigsten ausgelasteten Kandidaten -> gleichmaessige
    Verteilung (FA-08). Gibt die Trainer-Zeile oder None zurueck.
    """
    kandidaten = con.execute(
        "SELECT * FROM trainer WHERE id != ? AND krank = 0",
        (ausser_trainer_id,)).fetchall()
    verfuegbar = [t for t in kandidaten
                  if trainer_verfuegbar(con, t, woche, tag, uhrzeit, studio_id)]
    if not verfuegbar:
        return None
    verfuegbar.sort(key=lambda t: wochenstunden(con, t["id"], woche))
    return verfuegbar[0]


# ---- Geschaeftsprozess 5.2: Wochenplan generieren -----------------------

def generiere_wochenplan(con, woche, studio_ids=None, seed=None):
    """
    Erzeugt automatisch einen Wochenplan fuer die angegebene KW (FA-05).
    Beruecksichtigt Wochenstundenlimit, Fahrzeitpuffer und keine
    Doppelbelegung; verteilt Trainer gleichmaessig auf die Studios
    (FA-08). Findet sich kein Trainer, wird der Kurs als ausgefallen
    markiert (FA-10).

    Rueckgabe: dict mit Kennzahlen (geplant, ausgefallen).
    """
    if seed is not None:
        random.seed(seed)

    if studio_ids is None:
        studio_ids = [s["id"] for s in con.execute("SELECT id FROM studios")]

    kurse = con.execute("SELECT * FROM kurse").fetchall()
    if not kurse:
        return {"geplant": 0, "ausgefallen": 0}

    # Bestehenden Plan dieser KW fuer die betroffenen Studios entfernen
    for sid in studio_ids:
        con.execute("DELETE FROM plaene WHERE woche=? AND studioId=?", (woche, sid))
    con.commit()

    def lege_kurs_an(tag, uhrzeit, sid, kurs, raum):
        """Plant einen Kurs in einem bestimmten Raum ein; markiert ihn als
           ausgefallen, falls kein Trainer verfuegbar ist.
           Gibt (geplant, ausgefallen) als 0/1 zurueck."""
        trainer = finde_ersatztrainer(con, woche, tag, uhrzeit, sid,
                                      ausser_trainer_id=-1)
        if trainer is not None:
            con.execute(
                """INSERT INTO plaene (woche, tag, uhrzeit, raum, trainerId,
                   studioId, kursId, ausgefallen, vertretung)
                   VALUES (?,?,?,?,?,?,?,0,0)""",
                (woche, tag, uhrzeit, raum, trainer["id"], sid, kurs["id"]))
            return 1, 0
        con.execute(
            """INSERT INTO plaene (woche, tag, uhrzeit, raum, trainerId,
               studioId, kursId, ausgefallen, vertretung)
               VALUES (?,?,?,?,NULL,?,?,1,0)""",
            (woche, tag, uhrzeit, raum, sid, kurs["id"]))
        return 0, 1

    geplant = 0
    ausgefallen = 0
    parallel = 0
    kurs_index = 0
    # Wahrscheinlichkeit fuer einen zusaetzlichen Parallelkurs je weiterem Raum.
    # Jedes Studio hat 3 Raeume; Raum 1 ist der Primaerkurs, Raum 2/3 optional.
    raum_wahrscheinlichkeit = {2: PARALLEL_WAHRSCHEINLICHKEIT, 3: 0.12}

    for tag in sorted(TAGE):
        for uhrzeit in sorted(SLOTS):
            for sid in studio_ids:
                # Raum 1: Primaerkurs in diesem Zeitslot
                kurs = kurse[kurs_index % len(kurse)]
                kurs_index += 1
                g, a = lege_kurs_an(tag, uhrzeit, sid, kurs, 1)
                geplant += g
                ausgefallen += a

                # Raum 2 und 3: optionale Parallelkurse im SELBEN Studio zur
                # SELBEN Zeit (anderer Raum, anderer Trainer). Werden nur
                # angelegt, wenn noch ein weiterer Trainer frei ist.
                for raum in (2, 3):
                    if len(kurse) <= 1 or random.random() >= raum_wahrscheinlichkeit[raum]:
                        continue
                    kurs2 = kurse[kurs_index % len(kurse)]
                    kurs_index += 1
                    if kurs2["id"] == kurs["id"]:
                        kurs2 = kurse[kurs_index % len(kurse)]
                        kurs_index += 1
                    t2 = finde_ersatztrainer(con, woche, tag, uhrzeit, sid,
                                             ausser_trainer_id=-1)
                    if t2 is None:
                        break  # kein weiterer Trainer frei -> keine weiteren Raeume
                    con.execute(
                        """INSERT INTO plaene (woche, tag, uhrzeit, raum, trainerId,
                           studioId, kursId, ausgefallen, vertretung)
                           VALUES (?,?,?,?,?,?,?,0,0)""",
                        (woche, tag, uhrzeit, raum, t2["id"], sid, kurs2["id"]))
                    geplant += 1
                    parallel += 1
    con.commit()
    return {"geplant": geplant, "ausgefallen": ausgefallen, "parallel": parallel}


def wochen_daten(kw, jahr=None):
    """Liefert je Wochentag (1-6) das konkrete Datum als 'TT.MM.JJJJ'."""
    if jahr is None:
        jahr = date.today().year
    res = {}
    for tag in TAGE:
        try:
            res[tag] = date.fromisocalendar(jahr, kw, tag).strftime("%d.%m.%Y")
        except ValueError:
            res[tag] = ""
    return res


# ---- Geschaeftsprozess 5.1: Krankmeldung --------------------------------

def betroffene_wochen_tage(von, bis):
    """
    Bildet einen Datumsbereich (von..bis, inkl.) auf die Menge der
    betroffenen (Kalenderwoche, Wochentag)-Paare ab. Sonntag (7) wird
    ausgelassen, da nicht verplant.
    """
    paare = set()
    tag = von
    while tag <= bis:
        iso = tag.isocalendar()      # (jahr, kw, wochentag 1=Mo..7=So)
        if iso[2] <= 6:
            paare.add((iso[1], iso[2]))
        tag += timedelta(days=1)
    return paare


def verarbeite_krankmeldung(con, trainer_id, von, bis):
    """
    Verarbeitet eine Krankmeldung fuer den gewaehlten Zeitraum (UC-03):

      1. Trainer wird als krank markiert.
      2. Fuer jeden betroffenen Kurs im Zeitraum wird ein Ersatztrainer
         gesucht (gleiches Studio, nicht krank, keine Doppelbelegung,
         Fahrzeitpuffer, Wochenstundenlimit).
      3. Ersatz gefunden  -> Kurs wird umgebucht (vertretung=1).
         Kein Ersatz      -> Kurs wird als ausgefallen markiert.

    Rueckgabe: dict mit Zusammenfassung (vertreten, ausgefallen, details).
    """
    # 1. Trainer als krank markieren
    con.execute("UPDATE trainer SET krank=1 WHERE id=?", (trainer_id,))
    con.commit()

    paare = betroffene_wochen_tage(von, bis)
    if not paare:
        return {"vertreten": 0, "ausgefallen": 0, "details": [],
                "personalmangel": False}

    bedingungen = []
    for (woche, tag) in paare:
        rows = con.execute(
            """SELECT * FROM plaene
               WHERE trainerId=? AND woche=? AND tag=? AND ausgefallen=0""",
            (trainer_id, woche, tag)).fetchall()
        bedingungen.extend(rows)

    vertreten = 0
    ausgefallen = 0
    details = []

    for kurs in bedingungen:
        ersatz = finde_ersatztrainer(
            con, kurs["woche"], kurs["tag"], kurs["uhrzeit"],
            kurs["studioId"], ausser_trainer_id=trainer_id)
        if ersatz is not None:
            con.execute(
                "UPDATE plaene SET trainerId=?, vertretung=1 WHERE id=?",
                (ersatz["id"], kurs["id"]))
            vertreten += 1
            details.append({"plan_id": kurs["id"], "status": "vertreten",
                            "ersatz": ersatz["name"]})
        else:
            con.execute(
                "UPDATE plaene SET ausgefallen=1 WHERE id=?", (kurs["id"],))
            ausgefallen += 1
            details.append({"plan_id": kurs["id"], "status": "ausgefallen",
                            "ersatz": None})
    con.commit()
    return {"vertreten": vertreten, "ausgefallen": ausgefallen,
            "details": details, "personalmangel": ausgefallen > 0}


def aktuelle_kw():
    """Aktuelle Kalenderwoche."""
    return date.today().isocalendar()[1]
