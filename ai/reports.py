"""
Enkel lagring av rapporter/publikationer som AI:n ska väga in.

Användaren klistrar in eller laddar upp text (t.ex. utdrag ur en HELCOM-rapport,
en ny studie). Vi sparar den som en JSON-fil i data/reports/. AI-lagret läser
sedan in all text som CACHAD kontext, så den blir billig att återanvända.

Att lägga till/ta bort publikationer är lösenordsskyddat i app.py (F-02).
Lagringen är atomär och kapplöpningssäker (se ai/_store.py, F-07).
"""

import os
import re
from datetime import datetime

from . import _store

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "reports")
MAX_CONTEXT_CHARS = 24000   # tak på hur mycket rapporttext som skickas till AI:n

MAX_TITLE = 120
MAX_TEXT = 200_000          # tak per publikation (skydd mot disk-flooding, F-03)
MAX_LANK = 500

_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def _first_url(*texts):
    """Första http(s)-länken i någon av texterna (för 'Länk »' i listan)."""
    for t in texts:
        m = _URL_RE.search(t or "")
        if m:
            return m.group(0).rstrip(".,;)")
    return ""


def _clean_excerpt(text, n=160):
    """Utdrag utan råa URL:er (de blir svårlästa) — länken visas separat istället."""
    return _URL_RE.sub("", text or "").strip()[:n]


def add_report(titel, text, lank=None):
    """Sparar en rapport. Valfri länk till dokumentet. Returnerar dess metadata."""
    text = (str(text) if text is not None else "").strip()
    if not text:
        raise ValueError("Tom rapport.")
    text = text[:MAX_TEXT]
    titel = (str(titel) if titel is not None else "").strip()[:MAX_TITLE] or "Namnlös rapport"
    # Länk: explicit angiven, annars första URL:en i titel/text.
    lank = (str(lank) if lank is not None else "").strip()[:MAX_LANK]
    if lank and not _URL_RE.match(lank):
        lank = ""  # bara giltiga http(s)-länkar
    lank = lank or _first_url(titel, text)
    tillagd = datetime.now().strftime("%Y-%m-%d %H:%M")
    obj = _store.create(REPORTS_DIR, lambda rid: {
        "id": rid, "titel": titel, "text": text, "lank": lank, "tillagd": tillagd})
    return {"id": obj["id"], "titel": titel, "tillagd": tillagd,
            "tecken": len(text), "lank": lank}


def list_reports():
    """Metadata för alla rapporter (utan hela texten)."""
    out = []
    for o in _store.load_all(REPORTS_DIR):
        text = o.get("text", "")
        out.append({"id": o["id"], "titel": o.get("titel", ""),
                    "tillagd": o.get("tillagd", ""),
                    "tecken": len(text), "utdrag": _clean_excerpt(text),
                    "lank": o.get("lank") or _first_url(o.get("titel", ""), text)})
    out.sort(key=lambda o: o.get("id", 0))
    return out


def delete_report(rid):
    return _store.delete(REPORTS_DIR, rid)


def reports_text(max_chars=MAX_CONTEXT_CHARS):
    """
    All rapporttext hopslagen (för AI-kontext), trunkerad till max_chars.
    Returnerar tom sträng om inga rapporter finns.
    """
    chunks = []
    for o in sorted(_store.load_all(REPORTS_DIR), key=lambda o: o.get("id", 0)):
        chunks.append(f"### {o.get('titel', '')}\n{o.get('text', '')}")
    full = "\n\n".join(chunks)
    return full[:max_chars]
