"""
Hälso-/återhämtnings-index för Östersjön.

Ett enda tal 0–100 som sammanfattar ekosystemets tillstånd, så att olika
strategier kan jämföras rättvist (t.ex. i Monte Carlo). Indexet väger samman
fyra delpoäng som var för sig är väl förankrade indikatorer i litteraturen:

  torsk  — rovfiskens biomassa (nyckelindikator för ett friskt Östersjön)
  syre   — bottensyret (döda bottnar = kollaps av bottenlevande liv)
  cyano  — cyanobakterieblomning (lågt = bra; övergödningens ansikte)
  balans — näringsvävens balans (straffar ett 'spigghav' = wasp-waist-regimskifte)

Talen är MODELLENHETER (relativa), inte ton. Målvärdena nedan är kalibrerade mot
modellens egna storleksordningar (se model/ecosystem.py självtest).
"""

import numpy as np

from . import species as S
from .zones import ZONES

# --- Målvärden för "friskt hav" (full delpoäng) och trösklar -----------------
TORSK_TARGET = 0.45     # total torskbiomassa som ger full poäng
KUST_TARGET = 1.2       # abborre + gädda (kustrovfisk) för full poäng
OXY_TARGET = 90.0       # bottensyre (medel över zoner) för full poäng
CYANO_HI = 30.0         # kraftig blomning → 0 poäng
CYANO_LO = 8.0          # låg nivå → full poäng

# Vikter (summerar till 1). Syret väger nu mindre (det är ändå en egen parameter
# man kan följa i graferna); istället väger kustrovfisken (abborre/gädda) in, som
# är en central indikator för kustekosystemets hälsa.
W = dict(torsk=0.30, kust=0.20, syre=0.15, cyano=0.20, balans=0.15)


def _annual_mean(arr, t, year):
    """Medelvärde av en tidsserie under året [year-1, year] (dämpar säsong)."""
    t = np.asarray(t)
    lo = max(0.0, year - 1.0)
    mask = (t >= lo) & (t <= year + 1e-9)
    if not mask.any():
        mask = t <= year + 1e-9   # ta allt fram till året om fönstret är tomt
    return float(np.asarray(arr)[mask].mean())


def totals_at(res, comp, year):
    """Årsmedel av total biomassa för ett kompartment vid ett givet år."""
    return _annual_mean(res["totals"][comp], res["t"], year)


def mean_bottom_o2(res, year):
    """Årsmedel av bottensyret, medel över alla zoner, vid ett givet år."""
    vals = [_annual_mean(res["series"][z]["O2b"], res["t"], year) for z in res["zones"]]
    return float(np.mean(vals))


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def health_at(res, year):
    """
    Beräknar hälso-indexet (0–100) och dess delpoäng vid ett givet år.
    Returnerar dict: {index, torsk, syre, cyano, balans}.
    """
    torsk = totals_at(res, "torsk", year)
    kust = totals_at(res, "abborre", year) + totals_at(res, "gadda", year)
    sill = totals_at(res, "sill", year)
    skarp = totals_at(res, "skarpsill", year)
    spigg = totals_at(res, "spigg", year)
    cyano = totals_at(res, "cyano", year)
    o2b = mean_bottom_o2(res, year)

    s_torsk = _clip01(torsk / TORSK_TARGET)
    s_kust = _clip01(kust / KUST_TARGET)
    s_syre = _clip01(o2b / OXY_TARGET)
    s_cyano = _clip01((CYANO_HI - cyano) / (CYANO_HI - CYANO_LO))
    # Balans: straffa spiggdominans bland planktonätarna (wasp-waist)
    planktiv = sill + skarp + spigg + 0.1
    s_balans = _clip01(1.0 - spigg / planktiv)

    idx = 100.0 * (W["torsk"] * s_torsk + W["kust"] * s_kust + W["syre"] * s_syre
                   + W["cyano"] * s_cyano + W["balans"] * s_balans)
    return {
        "index": round(idx, 1),
        "torsk": round(100 * s_torsk, 1),
        "kust": round(100 * s_kust, 1),
        "syre": round(100 * s_syre, 1),
        "cyano": round(100 * s_cyano, 1),
        "balans": round(100 * s_balans, 1),
    }


def health_series(res, step_years=1.0):
    """Hälso-indexet över tid (ett värde per år) — för graf/animering."""
    tmax = res["t"][-1]
    years = list(np.arange(step_years, tmax + 1e-9, step_years))
    return {"years": [round(y, 1) for y in years],
            "index": [health_at(res, y)["index"] for y in years]}


# --- Hälsa per zon -----------------------------------------------------------
# Samma formel som för hela havet, men beräknad på en enskild zons värden.
# Biomassa-målen skalas ner med antalet zoner (totalmålen är summor över alla
# zoner), så en enskild zons index blir jämförbart. Syret är redan per zon.
NZONES = len(ZONES)


def _zone_mean(res, zone, comp, year):
    return _annual_mean(res["series"][zone][comp], res["t"], year)


def zone_health_at(res, zone, year):
    """Hälso-index (0–100) för EN zon vid ett givet år."""
    torsk = _zone_mean(res, zone, "torsk", year)
    kust = _zone_mean(res, zone, "abborre", year) + _zone_mean(res, zone, "gadda", year)
    sill = _zone_mean(res, zone, "sill", year)
    skarp = _zone_mean(res, zone, "skarpsill", year)
    spigg = _zone_mean(res, zone, "spigg", year)
    cyano = _zone_mean(res, zone, "cyano", year)
    o2b = _zone_mean(res, zone, "O2b", year)

    s_torsk = _clip01(torsk / (TORSK_TARGET / NZONES))
    s_kust = _clip01(kust / (KUST_TARGET / NZONES))
    s_syre = _clip01(o2b / OXY_TARGET)
    s_cyano = _clip01((CYANO_HI - cyano * NZONES) / (CYANO_HI - CYANO_LO))
    planktiv = sill + skarp + spigg + 0.1
    s_balans = _clip01(1.0 - spigg / planktiv)

    idx = 100.0 * (W["torsk"] * s_torsk + W["kust"] * s_kust + W["syre"] * s_syre
                   + W["cyano"] * s_cyano + W["balans"] * s_balans)
    return round(idx, 1)


def zone_health_series(res, zone, step_years=1.0):
    """Hälso-indexet över tid för EN zon."""
    tmax = res["t"][-1]
    years = list(np.arange(step_years, tmax + 1e-9, step_years))
    return {"years": [round(y, 1) for y in years],
            "index": [zone_health_at(res, zone, y) for y in years]}
