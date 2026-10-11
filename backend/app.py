"""
Fit & Aktiv – Kurs- und Trainerverwaltung
Anwendungsschicht (Server) – Flask.

Routen / Steuerung der Web-Anwendung. Bindet die Geschaeftslogik
(domain.py) und die Datenhaltung (db.py) zusammen und rendert die
HTML-Oberflaeche (Praesentationsschicht). Rollenbasierter Zugriff
fuer Chef, Studio-Manager und Trainer (FA-01, FA-12, FA-13).
"""

from datetime import date
from functools import wraps

from flask import (Flask, g, session, request, redirect, url_for,
                   render_template, flash, abort)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import domain

app = Flask(__name__,
            template_folder="../frontend/templates",
            static_folder="../frontend/static")
app.config["SECRET_KEY"] = "fit-und-aktiv-swe-praktikum-2026"

# Verbindung am Request-Ende schliessen
app.teardown_appcontext(db.close_db)


# ----------------------------------------------------------------------
#  Benutzer / Authentifizierung
# ----------------------------------------------------------------------
@app.before_request
def lade_benutzer():
    """Aktuellen Benutzer aus der Session laden."""
    g.user = None
    uid = session.get("uid")
    if uid is not None:
        g.user = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*rollen):
    def deco(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login"))
            if g.user["rolle"] not in rollen:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return deco


@app.context_processor
def inject_constants():
    """Konstanten in allen Templates verfuegbar machen."""
    return dict(TAGE=domain.TAGE, TAGE_KURZ=domain.TAGE_KURZ,
                SLOTS=domain.SLOTS, akt_kw=domain.aktuelle_kw())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        passwort = request.form.get("password", "")
        user = db.query("SELECT * FROM users WHERE username=?",
                        (username,), one=True)
        if user and check_password_hash(user["password"], passwort):
            session.clear()
            session["uid"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Ungültige Zugangsdaten.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------------------
#  Dashboard (FA-15)
# ----------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    rolle = g.user["rolle"]
    kw = _int_arg("kw", domain.aktuelle_kw())
    kennzahlen = {}

    if rolle == "chef":
        kennzahlen = {
            "Trainer": db.query("SELECT COUNT(*) n FROM trainer", one=True)["n"],
            "Studios": db.query("SELECT COUNT(*) n FROM studios", one=True)["n"],
            "Kurstypen": db.query("SELECT COUNT(*) n FROM kurse", one=True)["n"],
            "Offene Krankmeldungen":
                db.query("SELECT COUNT(*) n FROM trainer WHERE krank=1",
                         one=True)["n"],
            f"Ausgefallene Kurse (KW {kw})":
                db.query("SELECT COUNT(*) n FROM plaene WHERE woche=? AND ausgefallen=1",
                         (kw,), one=True)["n"],
        }
    elif rolle == "manager":
        sid = g.user["studioId"]
        studio = db.query("SELECT * FROM studios WHERE id=?", (sid,), one=True)
        kennzahlen = {
            "Trainer im Studio":
                db.query("SELECT COUNT(*) n FROM trainer_studios WHERE studioId=?",
                         (sid,), one=True)["n"],
            "Kranke Trainer (Studio)":
                db.query("""SELECT COUNT(*) n FROM trainer t
                            JOIN trainer_studios ts ON ts.trainerId=t.id
                            WHERE ts.studioId=? AND t.krank=1""",
                         (sid,), one=True)["n"],
            f"Ausgefallene Kurse (KW {kw})":
                db.query("""SELECT COUNT(*) n FROM plaene
                            WHERE studioId=? AND woche=? AND ausgefallen=1""",
                         (sid, kw), one=True)["n"],
        }
        return render_template("dashboard.html", kennzahlen=kennzahlen,
                               studio=studio, kw=kw)
    else:  # trainer
        return redirect(url_for("mein_plan"))

    return render_template("dashboard.html", kennzahlen=kennzahlen, kw=kw)


# ----------------------------------------------------------------------
#  Wochenplan (FA-05, FA-14, FA-16)
# ----------------------------------------------------------------------
def _int_arg(name, default):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _baue_grid(studio_id, kw):
    """Erzeugt eine Gitterstruktur grid[uhrzeit][tag] = [Eintraege...]."""
    rows = db.query(
        """SELECT p.*, k.name AS kurs, t.name AS trainer
           FROM plaene p
           JOIN kurse k ON k.id = p.kursId
           LEFT JOIN trainer t ON t.id = p.trainerId
           WHERE p.studioId=? AND p.woche=?
           ORDER BY p.uhrzeit, p.tag""", (studio_id, kw))
    grid = {u: {t: [] for t in domain.TAGE} for u in domain.SLOTS}
    for r in rows:
        grid[r["uhrzeit"]][r["tag"]].append(r)
    return grid


@app.route("/wochenplan")
@login_required
def wochenplan():
    if g.user["rolle"] == "trainer":
        return redirect(url_for("mein_plan"))

    studios = db.query("SELECT * FROM studios ORDER BY id")
    if g.user["rolle"] == "manager":
        studio_id = g.user["studioId"]
        studios = [s for s in studios if s["id"] == studio_id]
    else:
        studio_id = _int_arg("studio", studios[0]["id"] if studios else 0)

    kw = _int_arg("kw", domain.aktuelle_kw())
    grid = _baue_grid(studio_id, kw)
    studio = db.query("SELECT * FROM studios WHERE id=?", (studio_id,), one=True)
    return render_template("wochenplan.html", studios=studios, studio=studio,
                           studio_id=studio_id, kw=kw, grid=grid,
                           daten=domain.wochen_daten(kw))


@app.route("/wochenplan/generieren", methods=["POST"])
@role_required("chef", "manager")
def wochenplan_generieren():
    kw = int(request.form.get("kw", domain.aktuelle_kw()))
    con = db.get_db()
    if g.user["rolle"] == "manager":
        ziel = [g.user["studioId"]]
    else:
        if request.form.get("alle") == "1":
            ziel = None  # alle Studios
        else:
            ziel = [int(request.form.get("studio"))]
    res = domain.generiere_wochenplan(con, kw, ziel)
    flash(f"Wochenplan für KW {kw} erzeugt: {res['geplant']} Kurse geplant, "
          f"{res['ausgefallen']} ausgefallen.", "success")
    studio_id = (g.user["studioId"] if g.user["rolle"] == "manager"
                 else (ziel[0] if ziel else
                       db.query("SELECT id FROM studios ORDER BY id", one=True)["id"]))
    return redirect(url_for("wochenplan", studio=studio_id, kw=kw))


# ----------------------------------------------------------------------
#  Trainer-Ansicht: eigener Plan + Krankmeldung (FA-13, UC-03)
# ----------------------------------------------------------------------
@app.route("/mein-plan")
@role_required("trainer")
def mein_plan():
    tid = g.user["trainerId"]
    trainer = db.query("SELECT * FROM trainer WHERE id=?", (tid,), one=True)
    kw = _int_arg("kw", domain.aktuelle_kw())
    rows = db.query(
        """SELECT p.*, k.name AS kurs, s.name AS studio
           FROM plaene p
           JOIN kurse k ON k.id=p.kursId
           JOIN studios s ON s.id=p.studioId
           WHERE p.trainerId=? AND p.woche=?
           ORDER BY p.tag, p.uhrzeit""", (tid, kw))
    grid = {u: {t: [] for t in domain.TAGE} for u in domain.SLOTS}
    for r in rows:
        grid[r["uhrzeit"]][r["tag"]].append(r)
    return render_template("mein_plan.html", trainer=trainer, kw=kw,
                           grid=grid, anzahl=len(rows),
                           daten=domain.wochen_daten(kw))


@app.route("/krankmeldung/selbst", methods=["POST"])
@role_required("trainer")
def krankmeldung_selbst():
    tid = g.user["trainerId"]
    _krankmeldung_durchfuehren(tid, redirect_view="mein_plan")
    return redirect(url_for("mein_plan"))


# ----------------------------------------------------------------------
#  Krankmeldung durch Chef / Manager (UC-03, FA-09, FA-10)
# ----------------------------------------------------------------------
@app.route("/krankmeldung", methods=["GET", "POST"])
@role_required("chef", "manager")
def krankmeldung():
    if g.user["rolle"] == "manager":
        sid = g.user["studioId"]
        trainer_liste = db.query(
            """SELECT t.* FROM trainer t
               JOIN trainer_studios ts ON ts.trainerId=t.id
               WHERE ts.studioId=? ORDER BY t.name""", (sid,))
    else:
        trainer_liste = db.query("SELECT * FROM trainer ORDER BY name")

    ergebnis = None
    if request.method == "POST":
        tid = int(request.form.get("trainer_id"))
        if g.user["rolle"] == "manager" and not domain.trainer_in_studio(
                db.get_db(), tid, g.user["studioId"]):
            abort(403)
        ergebnis = _krankmeldung_durchfuehren(tid, redirect_view=None)

    return render_template("krankmeldung.html", trainer_liste=trainer_liste,
                           ergebnis=ergebnis)


def _krankmeldung_durchfuehren(tid, redirect_view):
    """Gemeinsame Verarbeitung (Chef/Manager/Trainer)."""
    von_s = request.form.get("von", "")
    bis_s = request.form.get("bis", "")
    try:
        von = date.fromisoformat(von_s)
        bis = date.fromisoformat(bis_s)
    except ValueError:
        flash("Bitte einen gültigen Zeitraum (Von- und Bis-Datum) wählen.", "error")
        return None
    if bis < von:
        flash("Das Bis-Datum darf nicht vor dem Von-Datum liegen.", "error")
        return None

    trainer = db.query("SELECT * FROM trainer WHERE id=?", (tid,), one=True)
    if trainer is None:
        abort(404)
    if trainer["krank"]:
        flash(f"Hinweis: {trainer['name']} ist bereits als krank gemeldet.", "info")

    res = domain.verarbeite_krankmeldung(db.get_db(), tid, von, bis)
    msg = (f"Krankmeldung verarbeitet: {res['vertreten']} Kurs(e) vertreten, "
           f"{res['ausgefallen']} ausgefallen.")
    flash(msg, "success")
    if res["personalmangel"]:
        flash("Es konnten nicht alle Kurse vertreten werden – das verfügbare "
              "Personal reicht nicht aus. Bitte zusätzliche Mitarbeiter einstellen!",
              "warning")
    return res


# ----------------------------------------------------------------------
#  Verwaltung: Trainer (FA-02), Studios (FA-03), Kurstypen (FA-04)
#  -> ausschliesslich Chef
# ----------------------------------------------------------------------
@app.route("/verwaltung/trainer", methods=["GET", "POST"])
@role_required("chef")
def verwaltung_trainer():
    con = db.get_db()
    if request.method == "POST":
        aktion = request.form.get("aktion")
        if aktion == "neu":
            name = request.form.get("name", "").strip()
            typ = request.form.get("typ", "VZ")
            studios = request.form.getlist("studios")
            if name:
                tid = db.execute(
                    "INSERT INTO trainer (name, typ, krank) VALUES (?,?,0)",
                    (name, typ))
                for sid in studios:
                    db.execute(
                        "INSERT INTO trainer_studios (trainerId, studioId) VALUES (?,?)",
                        (tid, int(sid)))
                # Automatisch ein Login fuer den neuen Trainer anlegen
                # (Benutzername trainer<ID>, Standard-Passwort demo1234).
                db.execute(
                    "INSERT INTO users (username, password, rolle, name, trainerId) VALUES (?,?,?,?,?)",
                    (f"trainer{tid}", generate_password_hash("demo1234"), "trainer", name, tid))
                flash(f"Trainer „{name}“ angelegt – Login: trainer{tid} / demo1234.", "success")
        elif aktion == "bearbeiten":
            tid = int(request.form.get("id"))
            name = request.form.get("name", "").strip()
            typ = request.form.get("typ", "VZ")
            studios = request.form.getlist("studios")
            db.execute("UPDATE trainer SET name=?, typ=? WHERE id=?",
                       (name, typ, tid))
            db.execute("DELETE FROM trainer_studios WHERE trainerId=?", (tid,))
            for sid in studios:
                db.execute(
                    "INSERT INTO trainer_studios (trainerId, studioId) VALUES (?,?)",
                    (tid, int(sid)))
            flash(f"Trainer „{name}“ aktualisiert.", "success")
        elif aktion == "loeschen":
            tid = int(request.form.get("id"))
            db.execute("DELETE FROM trainer_studios WHERE trainerId=?", (tid,))
            db.execute("DELETE FROM plaene WHERE trainerId=?", (tid,))
            db.execute("DELETE FROM users WHERE trainerId=?", (tid,))
            db.execute("DELETE FROM trainer WHERE id=?", (tid,))
            flash("Trainer gelöscht.", "success")
        return redirect(url_for("verwaltung_trainer"))

    trainer = db.query(
        """SELECT t.*,
                  (SELECT GROUP_CONCAT(s.name, ', ')
                     FROM trainer_studios ts JOIN studios s ON s.id=ts.studioId
                    WHERE ts.trainerId=t.id) AS studios
           FROM trainer t ORDER BY t.name""")
    studios = db.query("SELECT * FROM studios ORDER BY name")
    zuordnung = {}
    for ts in db.query("SELECT * FROM trainer_studios"):
        zuordnung.setdefault(ts["trainerId"], set()).add(ts["studioId"])
    return render_template("verwaltung_trainer.html", trainer=trainer,
                           studios=studios, zuordnung=zuordnung)


@app.route("/verwaltung/studios", methods=["GET", "POST"])
@role_required("chef")
def verwaltung_studios():
    if request.method == "POST":
        aktion = request.form.get("aktion")
        if aktion == "neu":
            name = request.form.get("name", "").strip()
            adresse = request.form.get("adresse", "").strip()
            if name:
                db.execute("INSERT INTO studios (name, adresse) VALUES (?,?)",
                           (name, adresse))
                flash(f"Studio „{name}“ angelegt.", "success")
        elif aktion == "bearbeiten":
            sid = int(request.form.get("id"))
            db.execute("UPDATE studios SET name=?, adresse=? WHERE id=?",
                       (request.form.get("name", "").strip(),
                        request.form.get("adresse", "").strip(), sid))
            flash("Studio aktualisiert.", "success")
        elif aktion == "loeschen":
            sid = int(request.form.get("id"))
            db.execute("DELETE FROM trainer_studios WHERE studioId=?", (sid,))
            db.execute("DELETE FROM plaene WHERE studioId=?", (sid,))
            db.execute("DELETE FROM studios WHERE id=?", (sid,))
            flash("Studio gelöscht.", "success")
        return redirect(url_for("verwaltung_studios"))

    studios = db.query("SELECT * FROM studios ORDER BY id")
    return render_template("verwaltung_studios.html", studios=studios)


@app.route("/verwaltung/kurse", methods=["GET", "POST"])
@role_required("chef")
def verwaltung_kurse():
    if request.method == "POST":
        aktion = request.form.get("aktion")
        if aktion == "neu":
            name = request.form.get("name", "").strip()
            if name:
                db.execute("INSERT INTO kurse (name) VALUES (?)", (name,))
                flash(f"Kurstyp „{name}“ angelegt.", "success")
        elif aktion == "bearbeiten":
            db.execute("UPDATE kurse SET name=? WHERE id=?",
                       (request.form.get("name", "").strip(),
                        int(request.form.get("id"))))
            flash("Kurstyp aktualisiert.", "success")
        elif aktion == "loeschen":
            kid = int(request.form.get("id"))
            db.execute("DELETE FROM plaene WHERE kursId=?", (kid,))
            db.execute("DELETE FROM kurse WHERE id=?", (kid,))
            flash("Kurstyp gelöscht.", "success")
        return redirect(url_for("verwaltung_kurse"))

    kurse = db.query("SELECT * FROM kurse ORDER BY name")
    return render_template("verwaltung_kurse.html", kurse=kurse)


# ----------------------------------------------------------------------
#  Zugangsverwaltung: Benutzerkonten ansehen + Passwort/Benutzername
#  aendern (nur Chef). Unterstuetzt die rollenbasierte Anmeldung (FA-01).
# ----------------------------------------------------------------------
@app.route("/verwaltung/zugaenge", methods=["GET", "POST"])
@role_required("chef")
def verwaltung_zugaenge():
    if request.method == "POST":
        uid = int(request.form.get("id"))
        user = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
        if user is None:
            abort(404)
        neuer_name = request.form.get("username", "").strip()
        neues_pw = request.form.get("passwort", "")

        # Benutzernamen aendern (muss eindeutig bleiben)
        if neuer_name and neuer_name != user["username"]:
            if db.query("SELECT 1 FROM users WHERE username=? AND id<>?",
                        (neuer_name, uid), one=True):
                flash(f"Benutzername „{neuer_name}“ ist bereits vergeben.", "error")
            else:
                db.execute("UPDATE users SET username=? WHERE id=?", (neuer_name, uid))
                flash("Benutzername aktualisiert.", "success")

        # Passwort neu setzen – es wird ausschliesslich der Hash gespeichert
        if neues_pw:
            db.execute("UPDATE users SET password=? WHERE id=?",
                       (generate_password_hash(neues_pw), uid))
            flash(f"Passwort für „{neuer_name or user['username']}“ neu gesetzt.", "success")

        return redirect(url_for("verwaltung_zugaenge"))

    users = db.query(
        """SELECT * FROM users
           ORDER BY CASE rolle WHEN 'chef' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, id""")
    return render_template("zugaenge.html", users=users)


@app.errorhandler(403)
def forbidden(e):
    return render_template("fehler.html",
                           code=403,
                           text="Kein Zugriff – Ihre Rolle ist dafür nicht berechtigt."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("fehler.html", code=404,
                           text="Seite nicht gefunden."), 404


def _datenbank_ok():
    """Prueft, ob eine gueltige, befuellte und SCHEMA-AKTUELLE Datenbank
       vorhanden ist (sonst wird sie neu aufgebaut)."""
    import sqlite3
    if not db.db_exists():
        return False
    try:
        con = sqlite3.connect(db.DB_PATH)
        anzahl = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        spalten = [r[1] for r in con.execute("PRAGMA table_info(plaene)")]
        version = con.execute("PRAGMA user_version").fetchone()[0]
        con.close()
        # DB muss befuellt, schema-aktuell ('raum') UND versionsaktuell sein
        return anzahl > 0 and "raum" in spalten and version == db.SEED_VERSION
    except Exception:
        return False


if __name__ == "__main__":
    # Beim ersten Start (oder bei fehlender/ungueltiger DB) Demo-Daten anlegen.
    if not _datenbank_ok():
        import seed
        seed.seed()
    app.run(debug=True, port=5000)
