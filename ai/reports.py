"""
Enkel lagring av rapporter/underlag som AI:n ska väga in.

Användaren klistrar in eller laddar upp text (t.ex. utdrag ur en HELCOM-rapport,
en ny studie). Vi sparar den som en JSON-fil i data/reports/. AI-lagret läser
sedan in all text som CACHAD kontext, så den blir billig att återanvända.

Ingen databas behövs — en fil per rapport, id = löpnummer.
"""

import glob
import json
import os
import re
from datetime import datetime

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "reports")
MAX_CONTEXT_CHARS = 24000   # tak på hur mycket rapporttext som skickas till AI:n


def _ensure():
    os.makedirs(REPORTS_DIR, exist_ok=True)


def _path(rid):
    return os.path.join(REPORTS_DIR, f"{int(rid)}.json")


def _next_id():
    _ensure()
    ids = [int(re.match(r"(\d+)\.json", os.path.basename(p)).group(1))
           for p in glob.glob(os.path.join(REPORTS_DIR, "*.json"))]
    return (max(ids) + 1) if ids else 1


def add_report(titel, text):
    """Sparar en rapport. Returnerar dess metadata."""
    _ensure()
    text = (text or "").strip()
    titel = (titel or "Namnlös rapport").strip()[:120]
    if not text:
        raise ValueError("Tom rapport.")
    rid = _next_id()
    obj = {"id": rid, "titel": titel, "text": text,
           "tillagd": datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(_path(rid), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return {"id": rid, "titel": titel, "tillagd": obj["tillagd"], "tecken": len(text)}


def list_reports():
    """Metadata för alla rapporter (utan hela texten)."""
    _ensure()
    out = []
    for p in sorted(glob.glob(os.path.join(REPORTS_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            o = json.load(f)
        out.append({"id": o["id"], "titel": o["titel"], "tillagd": o.get("tillagd", ""),
                    "tecken": len(o["text"]), "utdrag": o["text"][:160]})
    return out


def delete_report(rid):
    p = _path(rid)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False


def reports_text(max_chars=MAX_CONTEXT_CHARS):
    """
    All rapporttext hopslagen (för AI-kontext), trunkerad till max_chars.
    Returnerar tom sträng om inga rapporter finns.
    """
    _ensure()
    chunks = []
    for p in sorted(glob.glob(os.path.join(REPORTS_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            o = json.load(f)
        chunks.append(f"### {o['titel']}\n{o['text']}")
    full = "\n\n".join(chunks)
    return full[:max_chars]
