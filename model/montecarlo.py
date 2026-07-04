"""
Monte Carlo: vilken FÖRVALTNINGSSTRATEGI ger bäst återhämtning på 10/20/50/100 år?

"Monte Carlo" = vi kör simuleringen många gånger och lottar varje gång de
osäkra modellparametrarna (naturen känner vi inte exakt). Då får vi inte bara
ETT svar utan en FÖRDELNING — hur säkert är resultatet? Osäkerheten kcommer från
sådant litteraturen inte fastställt precist (t.ex. hur starkt spiggen låser fast
regimskiftet, hur mycket fosfor de syrefria bottnarna läcker).

För varje lottning kör vi ALLA strategier från exakt samma "värld" (samma
lottade parametrar och samma inkörda hav), så jämförelsen blir rättvis.

Två biprodukter:
  * Nationalekonomiskt värde per strategi och land (via model/economics.py).
  * Känslighetsanalys → VAR mer forskning behövs mest (vilka osäkra parametrar
    styr utfallet mest → där är kunskapsluckan dyrast).

Parallelliseras över lottningarna med alla CPU-kärnor.
"""

import os
# Begränsa varje process till 1 BLAS-tråd — annars slåss de parallella
# lottningarna om kärnorna. Måste sättas INNAN numpy laddas.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from . import economics as ECON
from . import health as H
from . import species as S
from . import ecosystem as ECO
from .ecosystem import EcoParams, default_initial_state, _precompute, _rhs, SPINUP_YEARS
from .zones import ZONES, N_ZONES
from scipy.integrate import solve_ivp

CI = S.CI
N_COMP = S.N_COMP
HORIZONS = [10, 20, 50, 100]
MAX_YEARS = 100

# --- Förvaltningsstrategier (det beslutsfattarna kan påverka) ----------------
STRATEGIES = {
    "baslinje": {"namn": "Baslinje (dagens förvaltning)", "params": {}},
    "torskstopp": {"namn": "Stoppa torskfisket",
                   "params": {"fishing": {"torsk": 0.0}}},
    "minskad_overgodning": {"namn": "Minskad övergödning (halverad näring)",
                            "params": {"nutrient_load": 0.5}},
    "kombinerat": {"namn": "Kombinerat åtgärdspaket",
                   "params": {"nutrient_load": 0.5,
                              "fishing": {"torsk": 0.0, "skarpsill": 0.15}}},
    "intensivt_fiske": {"namn": "Intensivare fiske",
                        "params": {"fishing": {"torsk": 0.8, "skarpsill": 1.0}}},
}

# --- Osäkra modellparametrar som lottas (litteraturens verkliga kunskapsluckor)
# key = "modul.attribut" eller "fish.art.attribut". rel_sd = relativ spridning.
UNCERTAIN = [
    {"key": "species.MU_PHYTO", "namn": "Växtplanktons maxtillväxt",
     "rel_sd": 0.20, "why": "Tillväxthastigheten varierar med art, ljus och näring.",
     "source": "Tamminen & Andersen 2007"},
    {"key": "species.CYANO_FIX", "namn": "Cyanobakteriers blomningsbenägenhet",
     "rel_sd": 0.30, "why": "Kvävefixeringen och blomningarnas storlek är svårförutsagda.",
     "source": "Kahru & Elmgren 2014"},
    {"key": "species.G_ZOO", "namn": "Djurplanktons betning",
     "rel_sd": 0.25, "why": "Betningstrycket styr hur mycket alger som når fisken.",
     "source": "Rudstam et al. 1994"},
    {"key": "species.INTERNAL_LOAD", "namn": "Fosforläckage från syrefria bottnar",
     "rel_sd": 0.35, "why": "Den interna belastningen är en av de största osäkerheterna.",
     "source": "Conley et al. 2009"},
    {"key": "species.VEXCH_MAX", "namn": "Ventilation av bottenvattnet",
     "rel_sd": 0.30, "why": "Inflöden av salt syrerikt vatten är oregelbundna och svårmodellerade.",
     "source": "Mohrholz et al. 2015"},
    {"key": "ecosystem.HYP_MORT_TORSK", "namn": "Torskens känslighet för syrebrist",
     "rel_sd": 0.30, "why": "Hur hårt hypoxin slår mot torskrekryteringen är omdiskuterat.",
     "source": "Casini et al. 2016"},
    {"key": "species.SPIGG_LARVAL_PREDATION", "namn": "Spiggens grepp om torskynglen",
     "rel_sd": 0.30, "why": "Styrkan i wasp-waist-regimskiftet är dåligt kvantifierad.",
     "source": "Eklöf et al. 2020"},
    {"key": "fish.torsk.eff", "namn": "Torskens tillväxteffektivitet",
     "rel_sd": 0.20, "why": "Hur väl torsken omvandlar föda till biomassa varierar.",
     "source": "ICES WGBFAS"},
]


# --- Läs/skriv en parameter via sträng-nyckel --------------------------------
def _get(key):
    if key.startswith("fish."):
        _, sp, attr = key.split(".")
        return S.FISH[sp][attr]
    mod, attr = key.split(".")
    return getattr(S if mod == "species" else ECO, attr)


def _set(key, val):
    if key.startswith("fish."):
        _, sp, attr = key.split(".")
        S.FISH[sp][attr] = val
        return
    mod, attr = key.split(".")
    setattr(S if mod == "species" else ECO, attr, val)


# --- Snabb ODE-lösning för ensemblen (lite lösare toleranser = dubbelt snabbare)
def _solve(y0, p, years, n_out):
    pre = _precompute(p)
    t_eval = np.linspace(0, years, n_out)
    sol = solve_ivp(_rhs, (0, years), y0, args=(p, pre), method="LSODA",
                    t_eval=t_eval, rtol=1e-3, atol=1e-6, max_step=0.2)
    return sol.t, np.maximum(sol.y, 0.0)


def _res_from(t, Y):
    """Bygger ett litet 'resultat' (som simulate()) för health/economics."""
    YZ = Y.reshape(N_ZONES, N_COMP, -1)
    series = {z.key: {c: YZ[zi, CI[c], :] for c in S.COMPARTMENTS}
              for zi, z in enumerate(ZONES)}
    totals = {c: YZ[:, CI[c], :].sum(axis=0) for c in S.COMPARTMENTS}
    return {"t": t, "zones": [z.key for z in ZONES], "totals": totals, "series": series}


def _strategy_params(skey, cfg):
    """EcoParams för en strategi ovanpå den gemensamma stress-kontexten."""
    p = EcoParams(years=MAX_YEARS,
                  temp_delta=cfg["temp_delta"],
                  salinity_delta=cfg["salinity_delta"],
                  nutrient_load=cfg["nutrient_load"])
    ov = STRATEGIES[skey]["params"]
    if "nutrient_load" in ov:
        p.nutrient_load = ov["nutrient_load"]
    if "fishing" in ov:
        p.fishing = {**p.fishing, **ov["fishing"]}
    return p


def _run_draw(args):
    """En lottning: lotta osäkra parametrar, kör alla strategier, sammanställ."""
    draw_i, cfg = args
    rng = np.random.RandomState(cfg["seed0"] * 100000 + draw_i)

    # Lotta parametrarna (multiplikativt kring basvärdet) och applicera
    sample, saved = {}, {}
    for u in UNCERTAIN:
        base = _get(u["key"])
        saved[u["key"]] = base
        factor = float(np.clip(np.exp(rng.normal(0, u["rel_sd"])), 0.45, 2.2))
        _set(u["key"], base * factor)
        sample[u["key"]] = factor         # spara faktorn för känslighetsanalysen
    try:
        # Kör in havet EN gång (dagens förvaltning) — delas av alla strategier.
        # Varje lottning får sitt eget väderår (noise_seed) → bandet fångar även
        # mellanårsvariationen; alla strategier i samma lottning delar väder.
        base_p = EcoParams(noise_seed=draw_i)
        base_p.temp_delta = cfg["temp_delta"]; base_p.salinity_delta = cfg["salinity_delta"]
        _, y_spin = _solve(default_initial_state(), base_p, SPINUP_YEARS, 4)
        start = y_spin[:, -1]

        n_out = MAX_YEARS + 1  # årsupplösning räcker för horisonterna
        snaps = {}  # skey -> horizon -> snapshot
        health = {}
        for skey in STRATEGIES:
            p = _strategy_params(skey, cfg)
            p.noise_seed = draw_i          # samma väder för alla strategier i lottningen
            t, Y = _solve(start, p, MAX_YEARS, n_out)
            res = _res_from(t, Y)
            snaps[skey] = {h: ECON.snapshot_from_res(res, h) for h in HORIZONS}
            health[skey] = {h: H.health_at(res, h) for h in HORIZONS}

        base_snaps = snaps["baslinje"]
        per = {}
        for skey in STRATEGIES:
            per[skey] = {}
            for h in HORIZONS:
                val = ECON.value_by_country(snaps[skey][h])
                imp = ECON.improvement(snaps[skey][h], base_snaps[h])
                per[skey][h] = {"health": health[skey][h], "value": val, "improvement": imp}
        return {"sample": sample, "per": per}
    finally:
        for k, v in saved.items():
            _set(k, v)


def _avg_value(dicts):
    """Medelvärde av flera value_by_country-resultat."""
    lands = ECON.COUNTRIES
    out = {c: {"fiske": 0.0, "tjanster": 0.0, "total": 0.0} for c in lands}
    tot = 0.0
    for d in dicts:
        for c in lands:
            for k in ("fiske", "tjanster", "total"):
                out[c][k] += d["per_land"][c][k]
        tot += d["total_hav"]
    n = len(dicts)
    for c in lands:
        out[c] = {k: round(v / n, 1) for k, v in out[c].items()}
    return {"per_land": out, "total_hav": round(tot / n, 1)}


def _avg_improvement(dicts):
    lands = ECON.COUNTRIES
    out = {c: 0.0 for c in lands}
    tot = 0.0
    for d in dicts:
        for c in lands:
            out[c] += d["per_land"][c]
        tot += d["total_hav"]
    n = len(dicts)
    return {"per_land": {c: round(out[c] / n, 1) for c in lands},
            "total_hav": round(tot / n, 1)}


def run(draws=16, temp_delta=0.0, salinity_delta=0.0, nutrient_load=1.0, seed0=0):
    """
    Kör hela Monte Carlo-jämförelsen. Returnerar allt frontend behöver:
    hälsa (medel + osäkerhetsband), ekonomiskt värde och förbättring per land,
    bästa strategi per horisont, samt känslighetsanalys (forskningsbehov).
    """
    draws = int(max(4, min(draws, 60)))
    cfg = {"temp_delta": temp_delta, "salinity_delta": salinity_delta,
           "nutrient_load": nutrient_load, "seed0": seed0}
    tasks = [(i, cfg) for i in range(draws)]

    workers = min(draws, max(1, (os.cpu_count() or 4) - 2))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        draws_out = list(ex.map(_run_draw, tasks))

    resultat, basta = {}, {}
    for skey in STRATEGIES:
        halsa, varde, forb = {}, {}, {}
        for h in HORIZONS:
            idxs = np.array([d["per"][skey][h]["health"]["index"] for d in draws_out])
            parts = {p: round(float(np.mean(
                        [d["per"][skey][h]["health"][p] for d in draws_out])), 1)
                     for p in ("torsk", "kust", "syre", "cyano", "balans")}
            halsa[h] = {"mean": round(float(idxs.mean()), 1),
                        "p10": round(float(np.percentile(idxs, 10)), 1),
                        "p90": round(float(np.percentile(idxs, 90)), 1),
                        "parts": parts}
            varde[h] = _avg_value([d["per"][skey][h]["value"] for d in draws_out])
            forb[h] = _avg_improvement([d["per"][skey][h]["improvement"] for d in draws_out])
        resultat[skey] = {"namn": STRATEGIES[skey]["namn"],
                          "halsa": halsa, "varde": varde, "forbattring": forb}

    for h in HORIZONS:
        basta[h] = max(STRATEGIES, key=lambda s: resultat[s]["halsa"][h]["mean"])

    # Känslighetsanalys: korrelation mellan lottad parameter och baslinjens
    # hälsa vid 50 år → var osäkerheten betyder mest (forskningsbehov).
    y = np.array([d["per"]["baslinje"][50]["health"]["index"] for d in draws_out])
    kanslighet = []
    for u in UNCERTAIN:
        x = np.array([d["sample"][u["key"]] for d in draws_out])
        if x.std() < 1e-9 or y.std() < 1e-9:
            corr = 0.0
        else:
            corr = float(np.corrcoef(x, y)[0, 1])
        kanslighet.append({"key": u["key"], "namn": u["namn"],
                           "korrelation": round(corr, 2),
                           "why": u["why"], "source": u["source"]})
    kanslighet.sort(key=lambda k: abs(k["korrelation"]), reverse=True)

    return {
        "strategier": [{"key": k, "namn": v["namn"], "params": v["params"]}
                       for k, v in STRATEGIES.items()],
        "horisonter": HORIZONS,
        "lander": ECON.COUNTRIES,
        "resultat": resultat,
        "basta": basta,
        "kanslighet": kanslighet,
        "n_draws": draws,
        # Den gemensamma stress-kontexten som strategierna kördes i (från reglagen)
        "kontext": {"temp_delta": temp_delta, "salinity_delta": salinity_delta,
                    "nutrient_load": nutrient_load},
    }


if __name__ == "__main__":
    import time, json
    t0 = time.time()
    out = run(draws=12)
    print("Monte Carlo (12 lottningar) tog %.1f s\n" % (time.time() - t0))
    print("Bästa strategi per horisont:")
    for h in HORIZONS:
        b = out["basta"][h]
        print(f"  {h:3d} år: {out['resultat'][b]['namn']:40s} "
              f"hälsa {out['resultat'][b]['halsa'][h]['mean']}")
    print("\nHälsa per strategi (medel [p10–p90]):")
    for s in out["resultat"]:
        row = "  %-38s " % out["resultat"][s]["namn"]
        for h in HORIZONS:
            hh = out["resultat"][s]["halsa"][h]
            row += f"{h}år:{hh['mean']:4.0f}[{hh['p10']:.0f}-{hh['p90']:.0f}] "
        print(row)
    print("\nStörst forskningsbehov (känslighet):")
    for k in out["kanslighet"][:4]:
        print(f"  {k['namn']:42s} r={k['korrelation']:+.2f}  ({k['source']})")
    print("\nFörbättring vs baslinje @50 år, kombinerat (M€/år per land):")
    print(" ", json.dumps(out["resultat"]["kombinerat"]["forbattring"][50]["per_land"],
                          ensure_ascii=False))
