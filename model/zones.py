"""
Östersjöns ekologiska zoner.

Varje zon är en "låda" (box) i modellen med egen salthalt, temperatur och djup.
Zonerna byter vatten (och därmed näring + salt) med sina grannar. Havet har en
tydlig salthaltsgradient: nästan sött i norr (Bottenviken ~3 PSU) till marint
i söder vid de danska sunden (~18 PSU). PSU = salthalt i gram salt per kg vatten.

Värdena är litteraturförankrade riktvärden (HELCOM / SMHI-storleksordning), inte
exakta mätdata — syftet är en rimlig, pedagogisk förenkling.
"""

from dataclasses import dataclass, field


@dataclass
class Zone:
    key: str            # kort id
    name: str           # svenskt namn
    salinity: float     # baslinje-salthalt (PSU)
    temp_mean: float    # årsmedeltemp ytvatten (°C)
    temp_amp: float     # säsongsamplitud (°C) — sommar minus årsmedel
    depth: float        # medeldjup (m) — påverkar hur lätt syret tar slut på djupet
    has_deep_basin: bool  # djupa bassänger med syrefria bottnar (hypoxi-risk)
    # Position på en enkel schematisk karta (0–100 i x/y), för webb-visualiseringen
    x: float = 0.0
    y: float = 0.0


# De sex zonerna, norr → söder. temp_mean/amp ger säsong via en cosinuskurva i
# ecosystem.py (varm sommar, kall vinter). Bottenviken är kallast, sunden varmast.
ZONES = [
    Zone("bottenviken", "Bottenviken",        salinity=3.0,  temp_mean=4.0, temp_amp=9.0,  depth=40,  has_deep_basin=False, x=62, y=8),
    Zone("bottenhavet", "Bottenhavet",         salinity=5.5,  temp_mean=6.0, temp_amp=10.0, depth=70,  has_deep_basin=False, x=55, y=28),
    Zone("finska",      "Finska viken",        salinity=5.0,  temp_mean=6.5, temp_amp=11.0, depth=38,  has_deep_basin=False, x=80, y=42),
    Zone("egentliga",   "Egentliga Östersjön", salinity=7.0,  temp_mean=7.5, temp_amp=11.0, depth=200, has_deep_basin=True,  x=58, y=52),
    Zone("riga",        "Rigabukten",          salinity=6.0,  temp_mean=7.5, temp_amp=11.5, depth=26,  has_deep_basin=False, x=74, y=55),
    Zone("sunden",      "Öresund/Bälten",      salinity=18.0, temp_mean=9.0, temp_amp=10.0, depth=20,  has_deep_basin=False, x=40, y=74),
]

# Snabb uppslagning key → index i tillståndsvektorn
ZONE_INDEX = {z.key: i for i, z in enumerate(ZONES)}
N_ZONES = len(ZONES)

# Vattenutbyte mellan grannzoner (symmetriskt). Talet är en relativ utbyteshastighet
# (per år) — hur snabbt näring/salt blandas mellan lådorna. Sunden byter mest med
# Kattegatt (marint) och Egentliga Östersjön; Bottenviken är mest isolerad i norr.
# (zon_a, zon_b, hastighet)
EXCHANGE = [
    ("bottenviken", "bottenhavet", 0.20),
    ("bottenhavet", "egentliga",   0.18),
    ("egentliga",   "finska",      0.15),
    ("egentliga",   "riga",        0.12),
    ("egentliga",   "sunden",      0.22),
]

# Salthalt vid "randen" mot Kattegatt/Nordsjön (marint referensvärde som sunden
# dras mot). Används så att en klimat-utsötning inte gör hela havet sött orimligt snabbt.
OCEAN_SALINITY = 25.0


def neighbor_matrix():
    """Bygg en N_ZONES x N_ZONES-matris med utbyteshastigheter (symmetrisk)."""
    import numpy as np
    m = np.zeros((N_ZONES, N_ZONES))
    for a, b, rate in EXCHANGE:
        i, j = ZONE_INDEX[a], ZONE_INDEX[b]
        m[i, j] = rate
        m[j, i] = rate
    return m
