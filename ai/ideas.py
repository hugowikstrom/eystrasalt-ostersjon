"""
Idélåda: alla kan lämna idéer/förslag om simuleringen och Östersjön.

En fil per idé i data/ideas/. Ingen inloggning — namn är valfritt. id = löpnummer.
Lagringen är atomär och kapplöpningssäker (se ai/_store.py, F-07).
"""

import os
from datetime import datetime

from . import _store

IDEAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ideas")

MAX_NAME = 60
MAX_TEXT = 2000


def add_idea(namn, text):
    """Sparar en idé. Namn valfritt. Returnerar idén."""
    text = (str(text) if text is not None else "").strip()
    if not text:
        raise ValueError("Tom idé.")
    namn = (str(namn) if namn is not None else "").strip()[:MAX_NAME] or "Anonym"
    text = text[:MAX_TEXT]
    tid = datetime.now().strftime("%Y-%m-%d %H:%M")
    return _store.create(IDEAS_DIR, lambda iid: {
        "id": iid, "namn": namn, "text": text, "tid": tid})


def list_ideas():
    """Alla idéer, nyaste först."""
    out = _store.load_all(IDEAS_DIR)
    out.sort(key=lambda o: o.get("id", 0), reverse=True)
    return out


def delete(iid):
    return _store.delete(IDEAS_DIR, iid)
