"""
Idélåda: alla kan lämna idéer/förslag om simuleringen och Östersjön.

En fil per idé i data/ideas/. Ingen inloggning — namn är valfritt. id = löpnummer.
"""

import glob
import json
import os
import re
from datetime import datetime

IDEAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ideas")


def _ensure():
    os.makedirs(IDEAS_DIR, exist_ok=True)


def _path(iid):
    return os.path.join(IDEAS_DIR, f"{int(iid)}.json")


def _next_id():
    _ensure()
    ids = [int(re.match(r"(\d+)\.json", os.path.basename(p)).group(1))
           for p in glob.glob(os.path.join(IDEAS_DIR, "*.json"))]
    return (max(ids) + 1) if ids else 1


def add_idea(namn, text):
    """Sparar en idé. Namn valfritt. Returnerar idén."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Tom idé.")
    _ensure()
    namn = (namn or "Anonym").strip()[:60]
    iid = _next_id()
    obj = {"id": iid, "namn": namn, "text": text[:2000],
           "tid": datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(_path(iid), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return obj


def list_ideas():
    """Alla idéer, nyaste först."""
    _ensure()
    out = []
    for p in sorted(glob.glob(os.path.join(IDEAS_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    out.sort(key=lambda o: o["id"], reverse=True)
    return out


def delete(iid):
    p = _path(iid)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False
