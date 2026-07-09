"""
Ekologisk beroendematris: vem beror på vem i Östersjöns näringsväv.

Byggs ur DIET (predator → byte-preferenser) i species.py plus kretsloppets
processlänkar: primärproduktion (näring → plankton), dödsflödet (allt levande →
detritus) och nedbrytningen (detritus → näring). Matrisen används dels som
dokumentation, dels för den visuella beroendematrisen i webben (fliken "Ekologi").

Matrisens rad = KONSUMENT (den som beror på något), kolumn = RESURS (det den
beror på). Värdet är beroendets styrka (preferens 0–1). Kretsloppet sluts:
näring → växtplankton/cyanobakterier → djurplankton/bottenfauna → fisk →
toppredatorer → (död) → detritus → näring igen.
"""

from .species import DIET, DISPLAY, FISH, salinity_response

# Trofisk ordning, näringsbas → toppredator (syre-kompartmenten ingår ej i väven).
ORDER = ["N", "det", "phyto", "cyano", "zoo", "bentos", "sill", "skarpsill",
         "spigg", "mort", "flundra", "abborre", "gadda", "torsk", "lax", "fagel", "sal"]

# Funktionell grupp per kompartment (för färgläggning och gruppering i webben).
GROUP = {
    "N": "naring", "det": "detritus",
    "phyto": "producent", "cyano": "producent",
    "zoo": "primarkonsument", "bentos": "primarkonsument",
    "sill": "planktivor", "skarpsill": "planktivor", "spigg": "planktivor",
    "mort": "planktivor",
    "flundra": "bottenfisk",
    "abborre": "kustrovfisk", "gadda": "kustrovfisk",
    "torsk": "rovfisk", "lax": "rovfisk",
    "fagel": "toppredator", "sal": "toppredator",
}

GROUP_NAMN = {
    "naring": "Näring", "detritus": "Detritus/kadaver", "producent": "Producent",
    "primarkonsument": "Primärkonsument", "planktivor": "Planktonätare",
    "bottenfisk": "Bottenfisk (plattfisk)",
    "kustrovfisk": "Kustrovfisk", "rovfisk": "Rovfisk", "toppredator": "Toppredator",
}

EMOJI = {
    "N": "🧪", "det": "🍂", "phyto": "🌱", "cyano": "🦠", "zoo": "🦐",
    "bentos": "🦪", "sill": "🐟", "skarpsill": "🐠", "spigg": "🐡",
    "mort": "🐟", "flundra": "🥮", "abborre": "🎣", "gadda": "🐊",
    "torsk": "🐋", "lax": "🐟", "fagel": "🦆", "sal": "🦭",
}


def links():
    """Alla beroendelänkar (konsument → resurs) med styrka och typ."""
    out = []
    # Predation ur näringsväven (DIET).
    for pred, prey in DIET.items():
        if pred not in ORDER:
            continue
        for food, w in prey.items():
            if food in ORDER:
                out.append({"consumer": pred, "resource": food,
                            "w": float(w), "kind": "predation"})
    # Primärproduktion: växtplankton och cyanobakterier tar upp löst näring.
    out.append({"consumer": "phyto", "resource": "N", "w": 1.0, "kind": "uptake"})
    out.append({"consumer": "cyano", "resource": "N", "w": 0.5, "kind": "uptake"})  # fixerar delvis eget kväve
    # Kretsloppet sluts: allt levande blir detritus när det dör.
    for c in ORDER:
        if GROUP[c] not in ("naring", "detritus"):
            out.append({"consumer": "det", "resource": c, "w": 0.5, "kind": "doden"})
    # Nedbrytning: detritus bryts ned till löst näring igen.
    out.append({"consumer": "N", "resource": "det", "w": 1.0, "kind": "nedbrytning"})
    return out


def matrix():
    """Fullständig beroendematris + metadata för webben."""
    idx = {c: i for i, c in enumerate(ORDER)}
    n = len(ORDER)
    M = [[0.0] * n for _ in range(n)]
    lk = links()
    for l in lk:
        M[idx[l["consumer"]]][idx[l["resource"]]] = round(l["w"], 3)
    # Salthaltsnisch (optimum + bredd) för de arter som har en sådan — ger nord–syd.
    salt = {c: {"opt": FISH[c]["sal_opt"], "width": FISH[c]["sal_width"]}
            for c in ORDER if c in FISH}
    return {
        "order": ORDER,
        "display": {c: DISPLAY[c] for c in ORDER},
        "grupp": GROUP,
        "grupp_namn": GROUP_NAMN,
        "emoji": EMOJI,
        "matris": M,          # rad = konsument, kolumn = resurs
        "lankar": lk,
        "salt": salt,
    }


if __name__ == "__main__":
    m = matrix()
    print("Beroendematris (rad beror på kolumn):")
    hdr = "        " + " ".join(f"{c[:4]:>5}" for c in m["order"])
    print(hdr)
    for i, c in enumerate(m["order"]):
        row = " ".join(f"{v:5.2f}" if v else "    ·" for v in m["matris"][i])
        print(f"{c[:7]:>7} {row}")
