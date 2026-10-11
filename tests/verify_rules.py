import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
"""Prueft den generierten Wochenplan auf Verstoesse gegen die Planungsregeln."""
import sqlite3
import domain
import db

con = sqlite3.connect(db.DB_PATH)
con.row_factory = sqlite3.Row
SS = domain.SLOT_START_MIN
errs = []

# 1) Keine Doppelbelegung eines Trainers (gleiche Zeit)
for r in con.execute("""SELECT trainerId,woche,tag,uhrzeit,COUNT(*) c FROM plaene
   WHERE ausgefallen=0 AND trainerId IS NOT NULL
   GROUP BY trainerId,woche,tag,uhrzeit HAVING c>1"""):
    errs.append(f"Doppelbelegung Trainer {r['trainerId']} {r['woche']}/{r['tag']}/{r['uhrzeit']}")

# 2) Wochenstundenlimit (VZ 20 / TZ 10)
for t in con.execute("SELECT * FROM trainer"):
    for w in con.execute("SELECT DISTINCT woche FROM plaene"):
        n = con.execute("SELECT COUNT(*) c FROM plaene WHERE trainerId=? AND woche=? AND ausgefallen=0",
                        (t["id"], w["woche"])).fetchone()["c"]
        if n > domain.WOCHENLIMIT[t["typ"]]:
            errs.append(f"Limit ueberschritten: {t['name']} KW{w['woche']} {n}")

# 3) Fahrzeitpuffer (verschiedene Studios -> >=120 Min Startabstand)
rows = con.execute("SELECT trainerId,woche,tag,uhrzeit,studioId FROM plaene WHERE ausgefallen=0 AND trainerId IS NOT NULL").fetchall()
from collections import defaultdict
byday = defaultdict(list)
for r in rows:
    byday[(r["trainerId"], r["woche"], r["tag"])].append(r)
for key, lst in byday.items():
    for i in range(len(lst)):
        for j in range(i + 1, len(lst)):
            a, b = lst[i], lst[j]
            if a["studioId"] != b["studioId"] and abs(SS[a["uhrzeit"]] - SS[b["uhrzeit"]]) < 120:
                errs.append(f"Fahrzeitpuffer verletzt Trainer {a['trainerId']} {key}")

# 4) Trainer nur in zugeordneten Studios eingeplant
for r in rows:
    if not con.execute("SELECT 1 FROM trainer_studios WHERE trainerId=? AND studioId=?",
                       (r["trainerId"], r["studioId"])).fetchone():
        errs.append(f"Trainer {r['trainerId']} nicht Studio {r['studioId']} zugeordnet")

# 5) Raum nie doppelt belegt (gleiches Studio, gleiche Zeit, gleicher Raum)
for r in con.execute("""SELECT woche,tag,uhrzeit,studioId,raum,COUNT(*) c FROM plaene
   GROUP BY woche,tag,uhrzeit,studioId,raum HAVING c>1"""):
    errs.append(f"Raum doppelt belegt Studio {r['studioId']} {r['woche']}/{r['tag']}/{r['uhrzeit']} Raum {r['raum']}")

tot = con.execute("SELECT COUNT(*) c FROM plaene").fetchone()["c"]
aus = con.execute("SELECT COUNT(*) c FROM plaene WHERE ausgefallen=1").fetchone()["c"]
par = len(con.execute("SELECT 1 FROM plaene GROUP BY woche,tag,uhrzeit,studioId HAVING COUNT(*)>1").fetchall())
print(f"Plaene gesamt: {tot}, ausgefallen: {aus}, Slots mit Parallelkursen: {par}")
print("Regel-Verstoesse:", len(errs))
for e in errs[:10]:
    print("  -", e)
print("OK" if not errs else "FEHLER")
