import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from datetime import date
import sqlite3
import app as application
import domain
import db

app=application.app
app.config.update(TESTING=True)
c=app.test_client()

def login(u,p="demo1234"):
    return c.post("/login",data={"username":u,"password":p},follow_redirects=True)

results=[]
def check(name,cond): results.append((name,bool(cond)))

# Login falsch
r=c.post("/login",data={"username":"chef","password":"falsch"},follow_redirects=True)
check("Login mit falschem Passwort abgelehnt", "Ungültige" in r.get_data(as_text=True))

# Chef
r=login("chef")
check("Chef Login -> Dashboard", "Willkommen, Lisa Fit" in r.get_data(as_text=True))
check("Dashboard Kennzahlen (FA-15)", "Offene Krankmeldungen" in r.get_data(as_text=True))
r=c.get("/wochenplan"); check("Wochenplan erreichbar", r.status_code==200)
html=r.get_data(as_text=True)
check("Wochenplan zeigt Legende/Farben (FA-14)", "Vertretung" in html and "Ausgefallen" in html)
check("Wochenplan Studio-Filter (FA-16)", "name=\"studio\"" in html)
r=c.get("/verwaltung/trainer")
_con=sqlite3.connect(db.DB_PATH); _n=_con.execute("SELECT COUNT(*) FROM trainer").fetchone()[0]; _con.close()
check("Verwaltung Trainer (FA-02)", r.status_code==200 and f"Trainer ({_n})" in r.get_data(as_text=True))
r=c.get("/verwaltung/studios"); check("Verwaltung Studios (FA-03)", r.status_code==200)
r=c.get("/verwaltung/kurse"); check("Verwaltung Kurse (FA-04)", r.status_code==200)

# Plan generieren (FA-05)
r=c.post("/wochenplan/generieren",data={"kw":domain.aktuelle_kw(),"studio":"1"},follow_redirects=True)
check("Plan generieren", "erzeugt" in r.get_data(as_text=True))
c.get("/logout")

# Trainer-Rolle: kein Zugriff auf Verwaltung (FA-13/Rollen)
login("trainer1")
r=c.get("/verwaltung/trainer"); check("Trainer hat KEINEN Zugriff auf Verwaltung (403)", r.status_code==403)
r=c.get("/mein-plan"); check("Trainer sieht eigenen Plan", r.status_code==200 and "Mein Wochenplan" in r.get_data(as_text=True))

# Krankmeldung durch Trainer mit Zeitraum (UC-03, FA-09/10)
kw=domain.aktuelle_kw()
con=sqlite3.connect(db.DB_PATH); con.row_factory=sqlite3.Row
t1=con.execute("SELECT * FROM users WHERE username='trainer1'").fetchone()
tid=t1["trainerId"]
vorher=con.execute("SELECT COUNT(*) c FROM plaene WHERE trainerId=? AND woche=? AND ausgefallen=0",(tid,kw)).fetchone()["c"]
mo=date.fromisocalendar(date.today().year,kw,1)
sa=date.fromisocalendar(date.today().year,kw,6)
r=c.post("/krankmeldung/selbst",data={"von":mo.isoformat(),"bis":sa.isoformat()},follow_redirects=True)
con2=sqlite3.connect(db.DB_PATH); con2.row_factory=sqlite3.Row
krank=con2.execute("SELECT krank FROM trainer WHERE id=?",(tid,)).fetchone()["krank"]
check("Trainer nach Krankmeldung als krank markiert", krank==1)
rest=con2.execute("SELECT COUNT(*) c FROM plaene WHERE trainerId=? AND woche=? AND ausgefallen=0",(tid,kw)).fetchone()["c"]
check("Eigene Kurse nach Krankmeldung neu zugeteilt/ausgefallen", rest < vorher or vorher==0)
vert=con2.execute("SELECT COUNT(*) c FROM plaene WHERE woche=? AND vertretung=1",(kw,)).fetchone()["c"]
check("Mindestens eine Vertretung gefunden (FA-09)", vert>0)

print("\n=== TESTERGEBNISSE ===")
ok=0
for n,p in results:
    print(("PASS" if p else "FAIL")+"  "+n); ok+=p
print(f"\n{ok}/{len(results)} bestanden")
