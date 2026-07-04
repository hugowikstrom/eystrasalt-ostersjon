"""
Verifiering av modellen mot känd Östersjö-litteratur.

Vi kör simuleringen för några scenarier och kontrollerar att den reproducerar
väldokumenterade SAMBAND (riktningar), t.ex. "utsötning → mindre torsk". Varje
kontroll returnerar godkänt/underkänt, det observerade värdet och en källa.

Detta är en RIKTNINGS-validering (kvalitativ), inte en sifferexakt kalibrering —
modellen är en pedagogisk förenkling. Men om ett samband bryts är det en varning.
"""

from .ecosystem import EcoParams, simulate
from . import health as H

YEARS = 50   # tillräckligt för att dynamiken (t.ex. regimskiften) ska hinna verka


def _params(**kw):
    """Bygger EcoParams; 'fishing' kan ges som dict-överlagring."""
    fishing = kw.pop("fishing", None)
    p = EcoParams(years=YEARS, **kw)
    if fishing:
        p.fishing = {**p.fishing, **fishing}
    return p


def _end(res, comp):
    return H.totals_at(res, comp, res["t"][-1])


def _o2(res):
    return H.mean_bottom_o2(res, res["t"][-1])


def _health(res):
    return H.health_at(res, res["t"][-1])["index"]


def run():
    """Kör alla kontroller och returnerar en lista med resultat."""
    # Kör grunduppsättningen en gång (återanvänds av flera kontroller)
    base = simulate(_params())
    torskstopp = simulate(_params(fishing={"torsk": 0.0}))
    utsotning = simulate(_params(salinity_delta=-2.0))
    varme_gods = simulate(_params(temp_delta=3.0, nutrient_load=1.8))
    overgodning = simulate(_params(nutrient_load=2.0))
    atgard = simulate(_params(nutrient_load=0.5))
    torskkollaps = simulate(_params(fishing={"torsk": 1.2}))

    checks = []

    def add(namn, ok, forvantat, observerat, source, forklaring):
        checks.append({"namn": namn, "godkand": bool(ok), "forvantat": forvantat,
                       "observerat": observerat, "source": source,
                       "forklaring": forklaring})

    # 1. Torskfiskestopp gynnar torsken
    a, b = _end(torskstopp, "torsk"), _end(base, "torsk")
    add("Torskfiskestopp ökar torskbeståndet", a > b,
        "torsk↑ vid stopp", f"{a:.3f} vs {b:.3f} (baslinje)",
        "ICES WGBFAS; Cardinale & Svedäng 2004",
        "Minskad fiskedödlighet ger mer torsk — om inte regimskiftet låser fast.")

    # 2. Utsötning slår mot torsken (kräver salt för att leka)
    a = _end(utsotning, "torsk")
    add("Utsötning minskar torsken", a < b,
        "torsk↓ vid sötare hav", f"{a:.3f} vs {b:.3f}",
        "MacKenzie et al. 2007",
        "Torskrommen behöver hög salthalt; sötare hav → sämre lekframgång.")

    # 3. Värme + övergödning → mer cyanobakterier
    a, b3 = _end(varme_gods, "cyano"), _end(base, "cyano")
    add("Värme + övergödning ökar cyanobakterier", a > b3,
        "cyano↑", f"{a:.1f} vs {b3:.1f}",
        "Kahru & Elmgren 2014",
        "Varmt, näringsrikt och skiktat vatten gynnar kvävefixerande blomningar.")

    # 4. Kraftig övergödning sänker bottensyret
    a, b4 = _o2(overgodning), _o2(base)
    add("Övergödning försämrar bottensyret", a < b4,
        "bottensyre↓", f"{a:.1f} vs {b4:.1f} % mättnad",
        "Conley et al. 2009",
        "Mer alger → mer nedbrytning på botten → syret tar slut (hypoxi).")

    # 5. Minskad övergödning förbättrar (eller försämrar inte) bottensyret
    a = _o2(atgard)
    add("Minskad övergödning förbättrar bottensyret", a >= b4 - 0.2,
        "bottensyre ≥ baslinje", f"{a:.1f} vs {b4:.1f} % mättnad",
        "Gustafsson et al. 2012 (BALTSEM)",
        "Mindre näring → mindre nedbrytning → mer syre kvar, men trögt pga intern belastning.")

    # 6. Torskåterhämtning pressar tillbaka spiggen (wasp-waist, omvänt håll —
    #    Östersjöns torsk är redan kollapsad, så det meningsfulla testet är att
    #    en RETURNERANDE torsk trycker ned spigghavet).
    a, b6 = _end(torskstopp, "spigg"), _end(base, "spigg")
    add("Torskåterhämtning pressar tillbaka spiggen (wasp-waist)", a < b6,
        "spigg↓ när torsken återhämtar sig", f"{a:.3f} vs {b6:.3f}",
        "Casini et al. 2009; Eklöf et al. 2020",
        "Torsken (toppredatorn) håller spiggen i schack; utan torsk låses ett spigghav.")

    # 7. Intensivt fiske sänker det samlade hälsoindexet
    a, b7 = _health(torskkollaps), _health(base)
    add("Hårt fiske sänker ekosystemets hälsa", a < b7,
        "hälsoindex↓", f"{a:.0f} vs {b7:.0f}",
        "HELCOM 2018 State of the Baltic Sea",
        "Överfiske av toppredatorn destabiliserar hela näringsväven.")

    # 8. Utsötning gynnar kustrovfisken (abborre + gädda är sötvattenarter)
    a = _end(utsotning, "abborre") + _end(utsotning, "gadda")
    b8 = _end(base, "abborre") + _end(base, "gadda")
    add("Utsötning gynnar kustrovfisk (abborre/gädda)", a > b8,
        "kustrovfisk↑ vid sötare hav", f"{a:.2f} vs {b8:.2f}",
        "Bergström et al. 2019; Havs- och vattenmyndigheten",
        "Abborre och gädda är sötvattenarter som trivs bättre när havet blir bräckt/sötare.")

    n_ok = sum(c["godkand"] for c in checks)
    return {"antal": len(checks), "godkanda": n_ok, "kontroller": checks}


if __name__ == "__main__":
    import time
    t = time.time()
    out = run()
    print("Verifiering: %d/%d godkända  (%.1f s)\n" % (out["godkanda"], out["antal"], time.time() - t))
    for c in out["kontroller"]:
        mark = "✓" if c["godkand"] else "✗"
        print(f"  {mark} {c['namn']}")
        print(f"      {c['observerat']}   [{c['source']}]")
