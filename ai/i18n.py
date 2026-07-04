"""
Flerspråkighet (i18n). Grundspråk är svenska; övriga Östersjöspråk + engelska
översätts av Claude vid första förfrågan och cachas till data/i18n/<kod>.json.

Språk: sv, fi (finska), et (estniska), lv (lettiska), lt (litauiska),
ru (ryska), pl (polska), de (tyska), da (danska), en (engelska).

Frontend hämtar en strängtabell {nyckel: text} för valt språk och byter ut
alla element med data-i18n="nyckel".
"""

import json
import os

from . import advisor

I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "i18n")

LANGS = [
    {"code": "sv", "name": "Svenska", "native": "Svenska"},
    {"code": "en", "name": "engelska", "native": "English"},
    {"code": "fi", "name": "finska", "native": "Suomi"},
    {"code": "et", "name": "estniska", "native": "Eesti"},
    {"code": "lv", "name": "lettiska", "native": "Latviešu"},
    {"code": "lt", "name": "litauiska", "native": "Lietuvių"},
    {"code": "ru", "name": "ryska", "native": "Русский"},
    {"code": "pl", "name": "polska", "native": "Polski"},
    {"code": "de", "name": "tyska", "native": "Deutsch"},
    {"code": "da", "name": "danska", "native": "Dansk"},
]
LANG_NAME = {l["code"]: l["name"] for l in LANGS}


def _ensure():
    os.makedirs(I18N_DIR, exist_ok=True)


def base_strings():
    """Svenska grundtabellen (facit)."""
    with open(os.path.join(I18N_DIR, "sv.json"), encoding="utf-8") as f:
        return json.load(f)


def get(code):
    """
    Strängtabell för ett språk. Svenska returneras direkt; övriga läses från cache
    eller översätts (och cachas). Faller tillbaka på svenska om översättning saknas.
    """
    _ensure()
    sv = base_strings()
    if code == "sv" or code not in LANG_NAME:
        return sv
    cache = os.path.join(I18N_DIR, f"{code}.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
        # Fyll på ev. nya nycklar som saknas i cachen
        if all(k in data for k in sv):
            return data
    translated = advisor.translate_table(sv, LANG_NAME[code], code)
    if not translated:
        return sv  # AI ej tillgänglig → svenska
    merged = {**sv, **translated}
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False)
    return merged
