"""
Spara och ladda parameteruppsättningar (och kort resultat-sammanfattning) på servern.

En fil per sparad uppsättning i data/saved/. Frontend kan även spara LOKALT i
webbläsaren (localStorage) — det här är serversidan så att sparade körningar finns
kvar och kan delas mellan datorer. Ingen databas behövs; id = löpnummer.
Lagringen är atomär och kapplöpningssäker (se ai/_store.py, F-07).
"""

import json
import os
from datetime import datetime

from . import _store

SAVED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "saved")

MAX_NAME = 120
MAX_USER = 60
MAX_PARAMS_BYTES = 8000     # tak på params/summary-storlek (skydd mot uppsvälld JSON, F-03/F-04)


def _bounded_dict(value):
    """Tillåt bara dict-objekt av rimlig storlek (annars töm)."""
    if not isinstance(value, dict):
        return {}
    try:
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > MAX_PARAMS_BYTES:
            return {}
    except (TypeError, ValueError):
        return {}
    return value


def save(namn, params, summary=None, user=""):
    """Sparar en parameteruppsättning + valfri sammanfattning. Returnerar metadata."""
    namn = (str(namn) if namn is not None else "").strip()[:MAX_NAME] or "Namnlös körning"
    user = (str(user) if user is not None else "").strip()[:MAX_USER]
    params = _bounded_dict(params)
    summary = _bounded_dict(summary)
    sparad = datetime.now().strftime("%Y-%m-%d %H:%M")
    obj = _store.create(SAVED_DIR, lambda sid: {
        "id": sid, "namn": namn, "user": user, "params": params,
        "summary": summary, "sparad": sparad})
    return {"id": obj["id"], "namn": namn, "user": user, "sparad": sparad}


def list_saved(user=None):
    """
    Sparade uppsättningar. Ges 'user' returneras bara den användarens körningar
    (enkel, lösenordslös profil). Utan 'user' returneras alla.
    """
    want = (str(user) if user is not None else "").strip()
    out = []
    for o in _store.load_all(SAVED_DIR):
        if want and (o.get("user", "") != want):
            continue
        out.append({"id": o["id"], "namn": o.get("namn", ""), "user": o.get("user", ""),
                    "sparad": o.get("sparad", ""), "params": o.get("params", {}),
                    "summary": o.get("summary", {})})
    out.sort(key=lambda o: o.get("id", 0))
    return out


def delete(sid):
    return _store.delete(SAVED_DIR, sid)
