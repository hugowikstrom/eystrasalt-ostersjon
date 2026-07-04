"""
Nationalekonomisk värdering av Östersjöns tillstånd, fördelat på angränsande länder.

Idé: ett friskare hav är värt pengar. Vi räknar två slags värde per år:
  1. Fiske      — kommersiell fångst (torsk, sill/strömming, skarpsill/sprat).
  2. Ekosystem­tjänster (icke-marknad) — rekreation/turism, näringsrening,
     kustskydd, biologisk mångfald. Skalar med hur friskt havet är.

Värdena fördelas på länderna via varje zons "ägarandel" (kustlinje/EEZ).
En strategis VÄRDE = dess årsvärde minus baslinjens, per land.

OBS: siffrorna är i miljoner euro/år och bygger på GROVA litteraturförankrade
schabloner (BalticSTERN, HELCOM, ICES-storleksordningar). Modellens biomassor är
relativa enheter, så koefficienterna är kalibrerade mot modellens skala — det här
är storleksordningar för jämförelse mellan strategier, inte bokföring.
"""

from . import health as H

# Länder runt Östersjön (svenska namn)
COUNTRIES = ["Sverige", "Finland", "Estland", "Lettland", "Litauen",
             "Ryssland", "Polen", "Tyskland", "Danmark"]

# Varje zons värde fördelas på länder (andelar summerar till 1 per zon)
ZONE_COUNTRY_SHARES = {
    "bottenviken": {"Sverige": 0.50, "Finland": 0.50},
    "bottenhavet": {"Sverige": 0.55, "Finland": 0.45},
    "finska":      {"Finland": 0.45, "Estland": 0.30, "Ryssland": 0.25},
    "egentliga":   {"Sverige": 0.30, "Polen": 0.22, "Tyskland": 0.13,
                    "Litauen": 0.12, "Lettland": 0.13, "Estland": 0.10},
    "riga":        {"Lettland": 0.60, "Estland": 0.40},
    "sunden":      {"Sverige": 0.40, "Danmark": 0.45, "Tyskland": 0.15},
}

# Fiskevärde: miljoner €/år per modellenhet biomassa
VAL_TORSK = 400.0    # torsk: högt värde per enhet
VAL_SILL = 6.0       # sill/strömming: stor volym, lägre pris
VAL_SKARP = 30.0     # skarpsill/sprat
# Abborre och gädda: litet kommersiellt fiske men STORT fritidsfiske- och
# turismvärde (kustnära sportfiske) — därav högt värde per enhet.
VAL_ABBORRE = 120.0
VAL_GADDA = 150.0
VAL_LAX = 250.0      # lax: högt värde (kommersiellt + sportfiske)

# Ekosystemtjänster: maxvärde per zon och år (vid perfekt ekologisk kvalitet)
SERVICES_PER_ZONE_MAX = 700.0

DISCOUNT = 0.03      # diskonteringsränta för nuvärde (framtida värde väger mindre)


def _zone_quality(o2b, cyano):
    """Ekologisk kvalitet 0–1 för en zon (styr ekosystemtjänsternas värde)."""
    q_o2 = max(0.0, min(1.0, o2b / H.OXY_TARGET))
    q_cy = max(0.0, min(1.0, (H.CYANO_HI - cyano) / (H.CYANO_HI - H.CYANO_LO)))
    return 0.5 * q_o2 + 0.5 * q_cy


def snapshot_from_res(res, year):
    """Plockar ut zon-vis årsmedel av det ekonomin behöver, vid ett givet år."""
    snap = {}
    for z in res["zones"]:
        s = res["series"][z]
        snap[z] = {
            "torsk": H._annual_mean(s["torsk"], res["t"], year),
            "sill": H._annual_mean(s["sill"], res["t"], year),
            "skarpsill": H._annual_mean(s["skarpsill"], res["t"], year),
            "abborre": H._annual_mean(s["abborre"], res["t"], year),
            "gadda": H._annual_mean(s["gadda"], res["t"], year),
            "lax": H._annual_mean(s["lax"], res["t"], year),
            "cyano": H._annual_mean(s["cyano"], res["t"], year),
            "O2b": H._annual_mean(s["O2b"], res["t"], year),
        }
    return snap


def value_by_country(snapshot):
    """
    Årsvärde (M€/år) per land från ett zon-snapshot.
    Returnerar {land: {fiske, tjanster, total}} + 'total_hav'.
    """
    out = {c: {"fiske": 0.0, "tjanster": 0.0, "total": 0.0} for c in COUNTRIES}
    for z, v in snapshot.items():
        fiske = (VAL_TORSK * v["torsk"] + VAL_SILL * v["sill"] + VAL_SKARP * v["skarpsill"]
                 + VAL_ABBORRE * v["abborre"] + VAL_GADDA * v["gadda"] + VAL_LAX * v["lax"])
        tjanster = SERVICES_PER_ZONE_MAX * _zone_quality(v["O2b"], v["cyano"])
        for country, share in ZONE_COUNTRY_SHARES[z].items():
            out[country]["fiske"] += fiske * share
            out[country]["tjanster"] += tjanster * share
    total_hav = 0.0
    for c in out:
        out[c]["total"] = out[c]["fiske"] + out[c]["tjanster"]
        out[c] = {k: round(x, 1) for k, x in out[c].items()}
        total_hav += out[c]["total"]
    return {"per_land": out, "total_hav": round(total_hav, 1)}


def improvement(strategy_snapshot, baseline_snapshot):
    """
    Förbättring (M€/år) per land: strategins årsvärde minus baslinjens.
    Positivt = strategin är värd mer än att inte göra något.
    """
    sv = value_by_country(strategy_snapshot)["per_land"]
    bv = value_by_country(baseline_snapshot)["per_land"]
    diff = {}
    tot = 0.0
    for c in COUNTRIES:
        d = round(sv[c]["total"] - bv[c]["total"], 1)
        diff[c] = d
        tot += d
    return {"per_land": diff, "total_hav": round(tot, 1)}


def cumulative_value(res, years=None):
    """
    Nuvärde (diskonterat) av det totala havsvärdet över hela körningen.
    Ger en enda summa i miljoner € — 'vad hela förloppet är värt idag'.
    """
    if years is None:
        years = int(res["t"][-1])
    pv = 0.0
    for y in range(1, years + 1):
        annual = value_by_country(snapshot_from_res(res, y))["total_hav"]
        pv += annual / ((1 + DISCOUNT) ** y)
    return round(pv, 0)
