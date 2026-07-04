"""
Spara och ladda parameteruppsättningar (och kort resultat-sammanfattning) på servern.

En fil per sparad uppsättning i data/saved/. Frontend kan även spara LOKALT i
webbläsaren (localStorage) — det här är serversidan så att sparade körningar finns
kvar och kan delas mellan datorer. Ingen databas behövs; id = löpnummer.
"""

import glob
import json
import os
import re
from datetime import datetime

SAVED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "saved")


def _ensure():
    os.makedirs(SAVED_DIR, exist_ok=True)


def _path(sid):
    return os.path.join(SAVED_DIR, f"{int(sid)}.json")


def _next_id():
    _ensure()
    ids = [int(re.match(r"(\d+)\.json", os.path.basename(p)).group(1))
           for p in glob.glob(os.path.join(SAVED_DIR, "*.json"))]
    return (max(ids) + 1) if ids else 1


def save(namn, params, summary=None, user=""):
    """Sparar en parameteruppsättning + valfri sammanfattning. Returnerar metadata."""
    _ensure()
    namn = (namn or "Namnlös körning").strip()[:120]
    user = (user or "").strip()[:60]
    sid = _next_id()
    obj = {"id": sid, "namn": namn, "user": user, "params": params or {},
           "summary": summary or {}, "sparad": datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(_path(sid), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return {"id": sid, "namn": namn, "user": user, "sparad": obj["sparad"]}


def list_saved(user=None):
    """
    Sparade uppsättningar. Ges 'user' returneras bara den användarens körningar
    (enkel, lösenordslös profil). Utan 'user' returneras alla.
    """
    _ensure()
    want = (user or "").strip()
    out = []
    for p in sorted(glob.glob(os.path.join(SAVED_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            o = json.load(f)
        if want and (o.get("user", "") != want):
            continue
        out.append({"id": o["id"], "namn": o["namn"], "user": o.get("user", ""),
                    "sparad": o.get("sparad", ""), "params": o.get("params", {}),
                    "summary": o.get("summary", {})})
    return out


def delete(sid):
    p = _path(sid)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False
