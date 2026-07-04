"""
Förinställda stress-scenarier. Varje scenario returnerar en EcoParams som webben
kan köra direkt, plus en kort svensk beskrivning.
"""

from .ecosystem import EcoParams


def _baseline(years=30):
    return EcoParams(years=years)


SCENARIOS = {
    "baslinje": {
        "namn": "Dagens hav (baslinje)",
        "beskrivning": "Nuvarande förhållanden — referens att jämföra mot.",
        "params": lambda y: _baseline(y),
    },
    "torskstopp": {
        "namn": "Totalt torskfiskestopp",
        "beskrivning": "Allt torskfiske upphör. Testar om torsken återhämtar sig "
                       "eller om spiggen håller den nere (regimskifte).",
        "params": lambda y: _fishing(_baseline(y), torsk=0.0),
    },
    "hardtral": {
        "namn": "Intensiv trålning",
        "beskrivning": "Kraftigt ökat fisketryck på torsk och skarpsill.",
        "params": lambda y: _fishing(_baseline(y), torsk=1.2, skarpsill=1.1),
    },
    "klimat": {
        "namn": "Klimatuppvärmning +3 °C",
        "beskrivning": "Varmare hav → starkare skiktning, mer cyanobakterier och "
                       "sämre bottensyre.",
        "params": lambda y: EcoParams(years=y, temp_delta=3.0),
    },
    "overgodning": {
        "namn": "Kraftig övergödning",
        "beskrivning": "Fördubblad näringsbelastning → algblomning och syrefria bottnar.",
        "params": lambda y: EcoParams(years=y, nutrient_load=2.0),
    },
    "atgard": {
        "namn": "Minskad övergödning",
        "beskrivning": "Halverad näringstillförsel (åtgärdsprogram).",
        "params": lambda y: EcoParams(years=y, nutrient_load=0.5),
    },
    "utsotning": {
        "namn": "Klimat-utsötning −2 PSU",
        "beskrivning": "Sötare hav → torsken (som behöver salt för att fortplanta sig) "
                       "minskar, spigg och sill gynnas.",
        "params": lambda y: EcoParams(years=y, salinity_delta=-2.0),
    },
    "perfekt_storm": {
        "namn": "Perfekt storm",
        "beskrivning": "Uppvärmning + övergödning + hårt torskfiske samtidigt.",
        "params": lambda y: _fishing(
            EcoParams(years=y, temp_delta=3.0, nutrient_load=1.8), torsk=1.0),
    },
}


def _fishing(p: EcoParams, **kw):
    p.fishing = {**p.fishing, **kw}
    return p


def get_scenario(key, years=30):
    """Returnerar EcoParams för ett scenario, eller baslinje om nyckeln saknas."""
    sc = SCENARIOS.get(key)
    if sc is None:
        return _baseline(years)
    return sc["params"](years)


def _reglage(p: EcoParams):
    """Scenariots värden i samma form som webbens stress-reglage läser (readParams)."""
    return {
        "years": p.years, "temp_delta": p.temp_delta,
        "nutrient_load": p.nutrient_load, "salinity_delta": p.salinity_delta,
        "seal_hunt": p.seal_hunt, "bird_hunt": p.bird_hunt, "noise": p.noise,
        "fishing": dict(p.fishing),
    }


def list_scenarios():
    """Metadata för webbens scenario-meny. Inkluderar 'reglage' så att ett scenario
    kan sättas som stress-reglage i webben (och sedan finjusteras vidare)."""
    return [{"key": k, "namn": v["namn"], "beskrivning": v["beskrivning"],
             "reglage": _reglage(v["params"](30))}
            for k, v in SCENARIOS.items()]
