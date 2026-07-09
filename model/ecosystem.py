"""
Ekosystemets kärna: kopplade differentialekvationer (ODE:er) för hela näringskedjan
i alla zoner, löst över tid med scipy.

Tillståndet är en vektor med N_ZONES * N_COMP tal (11 kompartment × 6 zoner = 66).
`simulate(params)` kör först en inkörning (spin-up) till baslinjens jämvikt och
därefter det valda stress-scenariot — så att man ser förändringen från ett stabilt hav.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import solve_ivp

from . import species as S
from .zones import ZONES, N_ZONES, neighbor_matrix, OCEAN_SALINITY

CI = S.CI
N_COMP = S.N_COMP

# --- Förberäknade zon-arrayer (i zon-ordning) --------------------------------
TEMP_MEAN = np.array([z.temp_mean for z in ZONES])
TEMP_AMP = np.array([z.temp_amp for z in ZONES])
SAL_BASE = np.array([z.salinity for z in ZONES])
DEPTH = np.array([z.depth for z in ZONES])
DEEP = np.array([z.has_deep_basin for z in ZONES], dtype=float)
# Djupa bassänger samlar mer detritus på botten → mer syreförbrukning där nere
DEEP_CONS = np.where(DEEP > 0, S.DEEP_FACTOR, 1.0)
# Grundläggande skiktning per zon (djupa bassänger har starkt språngskikt)
STRAT_BASE = np.where(DEEP > 0, S.STRAT_DEEP, 0.5) + DEPTH / 150.0

# Baslinje-näringsbelastning per zon (relativ). Övergödda vikar i öst/syd högre.
BASE_LOAD = np.array([0.6, 0.8, 1.6, 1.2, 1.5, 1.0])
LOAD_SCALE = 6.0

MIX = neighbor_matrix()
MIX_SUM = MIX.sum(axis=1)

# Kompartment som blandas mellan zoner (löst/planktoniskt driver med vattnet)
MIXED = [CI["N"], CI["phyto"], CI["cyano"], CI["zoo"], CI["det"]]

HYP_THRESH = 30.0        # syrenivå under vilken hypoxi ger extra dödlighet
HYP_MORT_TORSK = 0.5     # torsk (bottenlevande) drabbas hårdast av syrebrist
HYP_MORT_ZOO = 0.3


@dataclass
class EcoParams:
    """Stress-reglagen som användaren skruvar på, plus körlängd."""
    years: float = 30.0
    temp_delta: float = 0.0        # klimatuppvärmning (°C)
    nutrient_load: float = 1.0     # multiplikator på näringsbelastning (1 = dagens)
    salinity_delta: float = 0.0    # klimat-utsötning (negativ = sötare hav)
    seal_hunt: float = 0.0         # extra säljakt (0 = fredad)
    bird_hunt: float = 0.0         # skyddsjakt/störning på sjöfågel/skarv (0 = fredad)
    noise: float = 0.7             # mellanårsvariation (väderbrus) — realistisk baslinje
    noise_seed: int = 0            # slumpfrö för bruset (samma frö = samma förlopp)
    fishing: dict = field(default_factory=lambda: dict(
        sill=0.2, skarpsill=0.3, spigg=0.05, abborre=0.1, gadda=0.1,
        torsk=0.2, lax=0.15))


def _forcing(t, p: EcoParams):
    """Temperatur (säsong + klimat) och salthalt per zon vid tiden t (år)."""
    light = 0.5 * (1 - np.cos(2 * np.pi * t))          # 0 vinter → 1 sommar
    temp = TEMP_MEAN + p.temp_delta - TEMP_AMP * np.cos(2 * np.pi * t)
    sal = np.clip(SAL_BASE + p.salinity_delta, 0.5, OCEAN_SALINITY)
    return light, temp, sal


def _precompute(p: EcoParams):
    """
    Salthaltsberoendet är konstant under en körning (salinity_delta är fast) —
    beräkna det EN gång istället för i varje ODE-steg. Ger stor fart.
    """
    sal = np.clip(SAL_BASE + p.salinity_delta, 0.5, OCEAN_SALINITY)
    # Torsken leker i det salta DJUPvattnet — djupa bassänger har saltare botten
    # än yta, så lekframgången styrs av en högre effektiv salthalt där.
    spawn_sal = np.clip(sal + DEEP * 5.0, 0.5, OCEAN_SALINITY)

    # Brus: mellanårsvariation i temperatur och näring. Vi lottar EN gång per körning
    # ett värde per år (knut) och interpolerar mjukt däremellan, så att ODE-lösaren
    # ser en kontinuerlig kurva. Samma frö → exakt samma väderförlopp.
    if p.noise > 0:
        rng = np.random.RandomState(int(p.noise_seed))
        knots = np.arange(0.0, float(p.years) + 2.0)
        temp_noise = rng.normal(0.0, p.noise, len(knots))            # °C, additivt
        load_noise = np.exp(rng.normal(0.0, 0.5 * p.noise, len(knots)))  # multiplikativt
    else:
        knots = temp_noise = load_noise = None

    return dict(
        sal=sal,
        sr_sill=np.array([S.salinity_response("sill", s) for s in sal]),
        sr_skarp=np.array([S.salinity_response("skarpsill", s) for s in sal]),
        sr_spigg=np.array([S.salinity_response("spigg", s) for s in sal]),
        sr_abborre=np.array([S.salinity_response("abborre", s) for s in sal]),
        sr_gadda=np.array([S.salinity_response("gadda", s) for s in sal]),
        sr_flundra=np.array([S.salinity_response("flundra", s) for s in sal]),
        sr_torsk=np.array([S.salinity_response("torsk", s) for s in sal]),
        sr_lax=np.array([S.salinity_response("lax", s) for s in sal]),
        sr_fagel=np.array([S.salinity_response("fagel", s) for s in sal]),
        repro=np.array([S.cod_reproduction_factor(s) for s in spawn_sal]),
        knots=knots, temp_noise=temp_noise, load_noise=load_noise,
    )


def _rhs(t, y, p: EcoParams, pre):
    """Beräknar förändringshastigheten dy/dt för hela tillståndet."""
    Y = np.maximum(y.reshape(N_ZONES, N_COMP), 0.0)  # inga negativa biomassor
    light = 0.5 * (1 - np.cos(2 * np.pi * t))        # 0 vinter → 1 sommar
    # Brus: sampla dagens väderavvikelse ur den förberäknade kurvan
    if pre["knots"] is not None:
        temp_noise = float(np.interp(t, pre["knots"], pre["temp_noise"]))
        load_noise = float(np.interp(t, pre["knots"], pre["load_noise"]))
    else:
        temp_noise, load_noise = 0.0, 1.0
    temp = TEMP_MEAN + p.temp_delta + temp_noise - TEMP_AMP * np.cos(2 * np.pi * t)
    qt = S.q10_factor(temp)

    N = Y[:, CI["N"]]; P = Y[:, CI["phyto"]]; CY = Y[:, CI["cyano"]]
    Z = Y[:, CI["zoo"]]; bentos = Y[:, CI["bentos"]]
    sill = Y[:, CI["sill"]]; skarp = Y[:, CI["skarpsill"]]; spigg = Y[:, CI["spigg"]]
    abborre = Y[:, CI["abborre"]]; gadda = Y[:, CI["gadda"]]
    flundra = Y[:, CI["flundra"]]
    torsk = Y[:, CI["torsk"]]; lax = Y[:, CI["lax"]]
    fagel = Y[:, CI["fagel"]]; sal_b = Y[:, CI["sal"]]
    O2 = Y[:, CI["O2"]]; O2b = Y[:, CI["O2b"]]; det = Y[:, CI["det"]]
    eps = 1e-9

    # --- Primärproduktion (var sin takkapacitet: självskuggning) ---
    crowd_p = np.clip(1.0 - P / S.PHYTO_CAP, 0.0, 1.0)
    crowd_c = np.clip(1.0 - CY / S.CYANO_CAP, 0.0, 1.0)
    gP = S.MU_PHYTO * qt * light * crowd_p * (N / (S.K_N + N)) * P
    temp_gate = 1.0 / (1.0 + np.exp(-(temp - S.CYANO_TEMP_MIN)))     # blommar i värme
    nut_cyano = S.CYANO_FIX + (1 - S.CYANO_FIX) * (N / (S.K_N_CYANO + N))
    gCY = S.MU_CYANO * qt * light * crowd_c * temp_gate * nut_cyano * CY

    # --- Djurplankton betar plankton (cyanobakterier äts ogärna) ---
    prey_zoo = P + S.CYANO_GRAZE * CY + eps
    graze = S.G_ZOO * qt * (prey_zoo / (S.K_PREY_ZOO + prey_zoo)) * Z
    grazeP = graze * P / prey_zoo
    grazeCY = graze * S.CYANO_GRAZE * CY / prey_zoo
    zoo_growth = S.ASSIM_ZOO * (grazeP + grazeCY)

    # --- Bottenfauna filtrerar växtplankton + detritus (viktig näringsrening) ---
    prey_b = P + det + eps
    filt = S.BENTOS_FILTER * qt * (prey_b / (S.BENTOS_KHALF + prey_b)) * bentos
    filtP = filt * P / prey_b
    filtD = filt * det / prey_b
    bentos_growth = S.BENTOS_ASSIM * filt

    # --- Planktonätande fisk betar djurplankton (salthaltssvar förberäknat) ---
    def fish_cons(name, sresp, B):
        f = S.FISH[name]
        return f["cons"] * qt * sresp * (Z / (f["khalf"] + Z)) * B

    cons_sill = fish_cons("sill", pre["sr_sill"], sill)
    cons_skarp = fish_cons("skarpsill", pre["sr_skarp"], skarp)
    cons_spigg = fish_cons("spigg", pre["sr_spigg"], spigg)
    zoo_pred = cons_sill + cons_skarp + cons_spigg

    # --- Flundra (plattfisk) betar bottenfauna + lite detritus (bottenlevande) ---
    ffl = S.FISH["flundra"]
    prey_fl = bentos + 0.2 * det + eps
    cons_fl = ffl["cons"] * qt * pre["sr_flundra"] * (prey_fl / (ffl["khalf"] + prey_fl)) * flundra
    flundra_growth = ffl["eff"] * cons_fl
    loss_bentos_fl = cons_fl * bentos / prey_fl
    loss_det_fl = cons_fl * (0.2 * det) / prey_fl

    # --- Torsk äter planktonätarna (även spigg och bottenfauna) ---
    ft = S.FISH["torsk"]
    prey_t = 0.8 * sill + 1.0 * skarp + 0.9 * spigg + 0.12 * bentos + eps
    cons_t = ft["cons"] * qt * pre["sr_torsk"] * (prey_t / (ft["khalf"] + prey_t)) * torsk
    # torskrekrytering kräver salt; spiggen äter torskynglen (wasp-waist)
    repro = pre["repro"]
    larval_supp = S.SPIGG_LARVAL_PREDATION * spigg / (5.0 + spigg)
    torsk_growth = ft["eff"] * cons_t * repro * (1.0 - np.clip(larval_supp, 0, 0.95))
    # fördela torskens predation på bytena
    loss_sill_t = cons_t * (0.8 * sill) / prey_t
    loss_skarp_t = cons_t * (1.0 * skarp) / prey_t
    loss_spigg_t = cons_t * (0.9 * spigg) / prey_t
    loss_bentos_t = cons_t * (0.12 * bentos) / prey_t

    # --- Abborre (kustrovfisk) äter djurplankton + spigg + lite skarpsill ---
    fa = S.FISH["abborre"]
    prey_a = 0.4 * Z + 0.7 * spigg + 0.2 * skarp + eps
    cons_a = fa["cons"] * qt * pre["sr_abborre"] * (prey_a / (fa["khalf"] + prey_a)) * abborre
    coastal_supp = S.SPIGG_COASTAL_PREDATION * spigg / (5.0 + spigg)  # spiggen äter ynglen
    abborre_growth = fa["eff"] * cons_a * (1.0 - np.clip(coastal_supp, 0, 0.9))
    loss_zoo_a = cons_a * (0.4 * Z) / prey_a
    loss_spigg_a = cons_a * (0.7 * spigg) / prey_a
    loss_skarp_a = cons_a * (0.2 * skarp) / prey_a

    # --- Gädda (topp i kustkedjan) äter spigg + abborre + sill ---
    fg = S.FISH["gadda"]
    prey_g = 0.6 * spigg + 0.5 * abborre + 0.3 * sill + eps
    cons_g = fg["cons"] * qt * pre["sr_gadda"] * (prey_g / (fg["khalf"] + prey_g)) * gadda
    gadda_growth = fg["eff"] * cons_g * (1.0 - np.clip(coastal_supp, 0, 0.9))
    loss_spigg_g = cons_g * (0.6 * spigg) / prey_g
    loss_abborre_g = cons_g * (0.5 * abborre) / prey_g
    loss_sill_g = cons_g * (0.3 * sill) / prey_g

    # --- Sjöfågel (skarv m.fl.) äter kustfisk + bottenfauna ---
    ff = S.FISH["fagel"]
    prey_f = 0.7 * spigg + 0.5 * abborre + 0.4 * sill + 0.6 * bentos + eps
    cons_f = ff["cons"] * qt * pre["sr_fagel"] * (prey_f / (ff["khalf"] + prey_f)) * fagel
    fagel_growth = ff["eff"] * cons_f
    loss_spigg_f = cons_f * (0.7 * spigg) / prey_f
    loss_abborre_f = cons_f * (0.5 * abborre) / prey_f
    loss_sill_f = cons_f * (0.4 * sill) / prey_f
    loss_bentos_f = cons_f * (0.6 * bentos) / prey_f

    # --- Lax (pelagisk rovfisk) jagar sill/skarpsill/spigg ---
    fl = S.FISH["lax"]
    prey_l = 0.8 * sill + 0.6 * skarp + 0.3 * spigg + eps
    cons_l = fl["cons"] * qt * pre["sr_lax"] * (prey_l / (fl["khalf"] + prey_l)) * lax
    lax_growth = fl["eff"] * cons_l
    loss_sill_l = cons_l * (0.8 * sill) / prey_l
    loss_skarp_l = cons_l * (0.6 * skarp) / prey_l
    loss_spigg_l = cons_l * (0.3 * spigg) / prey_l

    # --- Säl äter fisk (inkl. lax) ---
    fs = S.FISH["sal"]
    prey_s = 0.6 * sill + 1.0 * torsk + 0.4 * skarp + 0.5 * lax + 0.3 * flundra + eps
    cons_s = fs["cons"] * qt * (prey_s / (fs["khalf"] + prey_s)) * sal_b
    sal_growth = fs["eff"] * cons_s
    loss_sill_s = cons_s * (0.6 * sill) / prey_s
    loss_torsk_s = cons_s * (1.0 * torsk) / prey_s
    loss_skarp_s = cons_s * (0.4 * skarp) / prey_s
    loss_lax_s = cons_s * (0.5 * lax) / prey_s
    loss_flundra_s = cons_s * (0.3 * flundra) / prey_s

    # --- Hypoxi: torsk lever nära botten → styrs av BOTTENsyret; djurplankton
    #     i den fria vattenmassan av ytsyret ---
    hyp_bottom = np.clip((HYP_THRESH - O2b) / HYP_THRESH, 0, 1)
    hyp_surface = np.clip((HYP_THRESH - O2) / HYP_THRESH, 0, 1)

    # --- Fiske (trålning/fångst) tar bort biomassa ur systemet ---
    fsh = p.fishing
    fish_sill = fsh.get("sill", 0.0) * sill
    fish_skarp = fsh.get("skarpsill", 0.0) * skarp
    fish_spigg = fsh.get("spigg", 0.0) * spigg
    fish_abborre = fsh.get("abborre", 0.0) * abborre
    fish_gadda = fsh.get("gadda", 0.0) * gadda
    fish_flundra = fsh.get("flundra", 0.0) * flundra
    fish_torsk = fsh.get("torsk", 0.0) * torsk
    fish_lax = fsh.get("lax", 0.0) * lax

    # --- Naturlig dödlighet + täthetsberoende bromsning (håller modellen stabil) ---
    m_sill = S.FISH["sill"]["mort"] * sill + 0.03 * sill ** 2
    m_skarp = S.FISH["skarpsill"]["mort"] * skarp + 0.03 * skarp ** 2
    m_spigg = S.FISH["spigg"]["mort"] * spigg + 0.03 * spigg ** 2
    m_abborre = S.FISH["abborre"]["mort"] * abborre + 0.04 * abborre ** 2
    m_gadda = S.FISH["gadda"]["mort"] * gadda + 0.05 * gadda ** 2
    # Flundra är bottenlevande → drabbas av syrefria bottnar (som torsken)
    m_flundra = (S.FISH["flundra"]["mort"] * flundra + 0.45 * flundra ** 2
                 + HYP_MORT_TORSK * hyp_bottom * flundra)
    m_torsk = S.FISH["torsk"]["mort"] * torsk + 0.03 * torsk ** 2 + HYP_MORT_TORSK * hyp_bottom * torsk
    m_lax = S.FISH["lax"]["mort"] * lax + 0.06 * lax ** 2
    # Bottenfaunan dör på syrefria bottnar (styrs av BOTTENsyret) → döda bottnar
    m_bentos = S.BENTOS_MORT * bentos + S.BENTOS_BRAKE * bentos ** 2 + S.BENTOS_HYP * hyp_bottom * bentos
    m_fagel = S.FISH["fagel"]["mort"] * (1 + p.bird_hunt) * fagel + 0.08 * fagel ** 2
    m_sal = S.FISH["sal"]["mort"] * (1 + p.seal_hunt) * sal_b + 0.05 * sal_b ** 2
    m_zoo = S.M_ZOO * Z + S.QUAD_ZOO * Z ** 2 + HYP_MORT_ZOO * hyp_surface * Z

    # --- Näring, detritus, syre ---
    uptake_N = gP + gCY * (1 - S.CYANO_FIX)
    decomp = S.DECOMP * qt * det
    load = BASE_LOAD * p.nutrient_load * LOAD_SCALE * load_noise  # brus på näringen
    # Intern belastning: syrefria bottnar läcker fosfor → mer näring (ond cirkel)
    anox = np.clip((S.ANOX_THRESH - O2b) / S.ANOX_THRESH, 0, 1)
    internal = S.INTERNAL_LOAD * anox * DEEP_CONS

    # Kretsloppet: ALLT som dör (inkl. säl och fågel) + osmält föda → detritus/kadaver
    det_in = (S.M_PHYTO * P + S.M_CYANO * CY + m_zoo + m_bentos
              + m_sill + m_skarp + m_spigg + m_abborre + m_gadda + m_flundra + m_torsk
              + m_lax + m_fagel + m_sal
              + (1 - S.ASSIM_ZOO) * graze
              + (1 - S.BENTOS_ASSIM) * filt
              + (1 - S.FISH["sill"]["eff"]) * cons_sill
              + (1 - S.FISH["skarpsill"]["eff"]) * cons_skarp
              + (1 - S.FISH["spigg"]["eff"]) * cons_spigg
              + (1 - fa["eff"]) * cons_a
              + (1 - fg["eff"]) * cons_g
              + (1 - ffl["eff"]) * cons_fl
              + (1 - ft["eff"]) * cons_t
              + (1 - fl["eff"]) * cons_l
              + (1 - ff["eff"]) * cons_f)

    # Vertikal syresättning: nedbrytningen sker mest på botten och tär på
    # BOTTENsyret. Ventilationen från ytan bromsas av skiktningen, som ökar med
    # temperaturen → klimatuppvärmning förvärrar de syrefria bottnarna. Bottnen är
    # en liten volym: ventilationen dränerar ytan lite (SURF_LOSS) men syresätter
    # botten mycket.
    strat = STRAT_BASE + S.STRAT_TEMP * np.maximum(temp - S.T_REF, 0)
    o2_prod = S.O2_PROD * (gP + gCY)              # produceras i ytan
    o2_reaer = S.O2_REAER * (S.O2_SAT - O2) / S.O2_SAT   # ytan mot atmosfären
    vent = S.VEXCH_MAX / (1.0 + strat) * (O2 - O2b)      # ventilation av bottenvatten
    o2_demand = S.O2_PER_DECOMP * decomp * DEEP_CONS     # syreåtgång på botten

    # --- Sätt ihop derivatorna ---
    d = np.zeros((N_ZONES, N_COMP))
    d[:, CI["N"]] = load + internal + decomp - uptake_N - S.N_LOSS * N
    d[:, CI["phyto"]] = gP - grazeP - filtP - S.M_PHYTO * P
    d[:, CI["cyano"]] = gCY - grazeCY - S.M_CYANO * CY
    d[:, CI["zoo"]] = zoo_growth - zoo_pred - loss_zoo_a - m_zoo
    d[:, CI["bentos"]] = bentos_growth - loss_bentos_t - loss_bentos_f - loss_bentos_fl - m_bentos
    d[:, CI["sill"]] = S.FISH["sill"]["eff"] * cons_sill - loss_sill_t - loss_sill_s - loss_sill_g - loss_sill_f - loss_sill_l - m_sill - fish_sill
    d[:, CI["skarpsill"]] = S.FISH["skarpsill"]["eff"] * cons_skarp - loss_skarp_t - loss_skarp_s - loss_skarp_a - loss_skarp_l - m_skarp - fish_skarp
    d[:, CI["spigg"]] = S.FISH["spigg"]["eff"] * cons_spigg - loss_spigg_t - loss_spigg_a - loss_spigg_g - loss_spigg_f - loss_spigg_l - m_spigg - fish_spigg
    d[:, CI["abborre"]] = abborre_growth - loss_abborre_g - loss_abborre_f - m_abborre - fish_abborre
    d[:, CI["gadda"]] = gadda_growth - m_gadda - fish_gadda
    d[:, CI["flundra"]] = flundra_growth - loss_flundra_s - m_flundra - fish_flundra
    d[:, CI["torsk"]] = torsk_growth - loss_torsk_s - m_torsk - fish_torsk
    d[:, CI["lax"]] = lax_growth - loss_lax_s - m_lax - fish_lax
    d[:, CI["fagel"]] = fagel_growth - m_fagel
    d[:, CI["sal"]] = sal_growth - m_sal
    d[:, CI["O2"]] = o2_prod + o2_reaer - S.SURF_LOSS * vent
    d[:, CI["O2b"]] = vent - o2_demand
    d[:, CI["det"]] = det_in - decomp - filtD - loss_det_fl - S.DET_BURIAL * det

    # --- Liten invandring: håller arter från att dö ut permanent (kan återhämtas) ---
    for c in ["phyto", "cyano", "zoo", "bentos", "sill", "skarpsill", "spigg",
              "abborre", "gadda", "flundra", "torsk", "lax", "fagel", "sal"]:
        d[:, CI[c]] += S.IMMIG

    # --- Vattenutbyte mellan zoner (blandar löst näring + plankton) ---
    for c in MIXED:
        col = Y[:, c]
        d[:, c] += MIX.dot(col) - col * MIX_SUM

    return d.reshape(-1)


# --- Trofinivåer: vilka arter hör till vilken nivå i näringspyramiden ---------
# Kretsloppet: näring → producenter → ... → toppredatorer → (död) → detritus → näring.
TROPHIC = [
    ("Näring (näringssalter)", ["N"]),
    ("Primärproducenter", ["phyto", "cyano"]),
    ("Djurplankton & bottenfauna", ["zoo", "bentos"]),
    ("Plankton- & bottenätande fisk", ["sill", "skarpsill", "spigg", "flundra"]),
    ("Kustrovfisk (abborre/gädda)", ["abborre", "gadda"]),
    ("Rovfisk (torsk/lax)", ["torsk", "lax"]),
    ("Toppredatorer (fågel/säl)", ["fagel", "sal"]),
    ("Detritus/kadaver → nedbrytning", ["det"]),
]


def _uttag_and_trofi(YZ, t, p):
    """
    Räknar (per år) dels UTTAGET ur havet uppdelat på källa (fiske/säl/skarv),
    dels total biomassa per TROFINIVÅ. Uttaget är borttagshastigheten (biomassa/år);
    säldelen är en approximation (säsong och brus utelämnas för överskådlighet).
    """
    t = np.asarray(t)
    years = list(range(1, int(round(t[-1])) + 1))

    # Temperaturfaktor vid årsmedeltemperatur (för predations- och nedbrytningsapprox.)
    qt_year = S.q10_factor(TEMP_MEAN + p.temp_delta)
    fs = S.FISH["sal"]; ff = S.FISH["fagel"]
    f = p.fishing
    eps = 1e-9

    def zsum(Y, c):
        return float(Y[:, CI[c]].sum())

    fiske, sal_u, skarv, atervinning = [], [], [], []
    trofi = {namn: [] for namn, _ in TROPHIC}
    for y in years:
        # Årsmedel över fönstret [y-1, y] (dämpar säsongssvängningen)
        mask = (t >= y - 1.0) & (t <= y + 1e-9)
        if not mask.any():
            mask = np.argmin(np.abs(t - y)) == np.arange(len(t))
        Y = YZ[:, :, mask].mean(axis=2)  # (zon, kompartment) årsmedel
        # Fiske (människa): borttag = fisketryck × biomassa
        fi = sum(f.get(a, 0.0) * zsum(Y, a)
                 for a in ["sill", "skarpsill", "spigg", "abborre", "gadda", "torsk", "lax"])
        sill = Y[:, CI["sill"]]; skarp = Y[:, CI["skarpsill"]]; spigg = Y[:, CI["spigg"]]
        abborre = Y[:, CI["abborre"]]; torsk = Y[:, CI["torsk"]]; bentos = Y[:, CI["bentos"]]
        # Skarv/sjöfågel: predation på fisk + bottenfauna (Holling II)
        prey_f = 0.7 * spigg + 0.5 * abborre + 0.4 * sill + 0.6 * bentos + eps
        cons_f = ff["cons"] * qt_year * (prey_f / (ff["khalf"] + prey_f)) * Y[:, CI["fagel"]]
        # Säl: predation på fisk (Holling II)
        prey_s = 0.6 * sill + 1.0 * torsk + 0.4 * skarp + eps
        cons_s = fs["cons"] * qt_year * (prey_s / (fs["khalf"] + prey_s)) * Y[:, CI["sal"]]
        # Återvinning: nedbrytning av detritus/kadaver → näring (kretsloppet sluts)
        atv = float((S.DECOMP * qt_year * Y[:, CI["det"]]).sum())
        fiske.append(round(fi, 3)); skarv.append(round(float(cons_f.sum()), 3))
        sal_u.append(round(float(cons_s.sum()), 3)); atervinning.append(round(atv, 3))
        for namn, comps in TROPHIC:
            trofi[namn].append(round(sum(zsum(Y, c) for c in comps), 3))

    return (
        {"years": years, "fiske": fiske, "sal": sal_u, "skarv": skarv,
         "atervinning": atervinning},
        {"years": years, "nivaer": trofi, "ordning": [n for n, _ in TROPHIC]},
    )


def default_initial_state():
    """Startvärden per zon. Torsk startar bara i salt vatten (söder)."""
    Y = np.zeros((N_ZONES, N_COMP))
    for zi, z in enumerate(ZONES):
        s = z.salinity
        Y[zi, CI["N"]] = 3.0
        Y[zi, CI["phyto"]] = 5.0
        Y[zi, CI["cyano"]] = 1.0
        Y[zi, CI["zoo"]] = 4.0
        Y[zi, CI["bentos"]] = 3.0
        Y[zi, CI["sill"]] = max(0.1, 4.0 * S.salinity_response("sill", s))
        Y[zi, CI["skarpsill"]] = max(0.1, 4.0 * S.salinity_response("skarpsill", s))
        Y[zi, CI["spigg"]] = max(0.1, 3.0 * S.salinity_response("spigg", s))
        # Kustrovfisk startar i bräckt/sött vatten (norr och kustnära)
        Y[zi, CI["abborre"]] = max(0.05, 3.0 * S.salinity_response("abborre", s))
        Y[zi, CI["gadda"]] = max(0.03, 2.0 * S.salinity_response("gadda", s))
        Y[zi, CI["flundra"]] = max(0.05, 1.0 * S.salinity_response("flundra", s))
        Y[zi, CI["torsk"]] = max(0.05, 3.0 * S.salinity_response("torsk", s) * S.cod_reproduction_factor(s))
        Y[zi, CI["lax"]] = max(0.03, 1.0 * S.salinity_response("lax", s))
        Y[zi, CI["fagel"]] = 0.4
        Y[zi, CI["sal"]] = 0.3
        Y[zi, CI["O2"]] = 90.0
        # Bottensyret startar lägre i djupa bassänger
        Y[zi, CI["O2b"]] = 40.0 if z.has_deep_basin else 80.0
        Y[zi, CI["det"]] = 2.0
    return Y.reshape(-1)


def _integrate(y0, p: EcoParams, years, n_out):
    pre = _precompute(p)
    t_eval = np.linspace(0, years, n_out)
    sol = solve_ivp(_rhs, (0, years), y0, args=(p, pre), method="LSODA",
                    t_eval=t_eval, rtol=1e-4, atol=1e-7, max_step=0.1)
    return sol.t, np.maximum(sol.y, 0.0)


SPINUP_YEARS = 25.0


def simulate(p: EcoParams):
    """
    Kör baslinje-inkörning + valt scenario. Returnerar tidsserier redo för webben.
    """
    base = EcoParams()  # neutralt läge (dagens hav)
    y0 = default_initial_state()
    _, y_spin = _integrate(y0, base, SPINUP_YEARS, 6)
    start = y_spin[:, -1]

    n_out = int(p.years * 12) + 1  # månadsupplösning
    t, Y = _integrate(start, p, p.years, n_out)
    YZ = Y.reshape(N_ZONES, N_COMP, -1)  # (zon, kompartment, tid)

    series = {}
    for zi, z in enumerate(ZONES):
        series[z.key] = {c: YZ[zi, CI[c], :].tolist() for c in S.COMPARTMENTS}

    totals = {c: YZ[:, CI[c], :].sum(axis=0).tolist() for c in S.COMPARTMENTS}

    # Miljö (temp/salthalt) per zon över tid — för kartans färgläggning
    env = {"temp": {}, "salinity": {}}
    temps, sals = [], []
    for ti in t:
        _, tp, sl = _forcing(ti, p)
        temps.append(tp); sals.append(sl)
    temps = np.array(temps); sals = np.array(sals)  # (tid, zon)
    for zi, z in enumerate(ZONES):
        env["temp"][z.key] = temps[:, zi].tolist()
        env["salinity"][z.key] = sals[:, zi].tolist()

    result = {
        "t": t.tolist(),
        "zones": [z.key for z in ZONES],
        "zone_names": {z.key: z.name for z in ZONES},
        "compartments": S.COMPARTMENTS,
        "display": S.DISPLAY,
        "units": S.UNIT,
        "series": series,
        "totals": totals,
        "env": env,
    }
    # Uttag ur havet (fiske/säl/skarv) + biomassa per trofinivå över tid
    uttak, trofi = _uttag_and_trofi(YZ, t, p)
    result["uttak"] = uttak
    result["trofi"] = trofi

    # Hälso-index (0–100) över tid — för graf och sammanfattning
    from . import health as H
    _step = max(0.5, p.years / 60.0)
    result["health"] = H.health_series(result, step_years=_step)
    # Hälsa per zon (beror på markerad region i kartan)
    result["health_zones"] = {z.key: H.zone_health_series(result, z.key, step_years=_step)
                              for z in ZONES}
    return result


if __name__ == "__main__":
    # Självtest: skriver ut årsmedel för sista året (inte vinterögonblicket).
    def mean_last_year(res, key, comp):
        vals = np.array(res["series"][key][comp][-12:])  # sista 12 månaderna
        return vals.mean()

    def tot_last_year(res, comp):
        return sum(mean_last_year(res, z, comp) for z in res["zones"])

    def summ(res, label):
        print(f"\n=== {label} (årsmedel sista året) ===")
        for c in ["phyto", "cyano", "zoo", "bentos", "sill", "skarpsill", "spigg",
                  "flundra", "abborre", "gadda", "torsk", "lax", "fagel", "sal"]:
            print(f"  {S.DISPLAY[c]:14s}: {tot_last_year(res, c):7.2f}")
        print("  Bottensyre per zon:")
        for z in res["zones"]:
            print(f"    {res['zone_names'][z]:20s}: {mean_last_year(res, z, 'O2b'):5.1f}"
                  f"   (ytsyre {mean_last_year(res, z, 'O2'):.0f})")

    summ(simulate(EcoParams(years=30)), "Baslinje")

    stop = EcoParams(years=40)
    stop.fishing["torsk"] = 0.0
    summ(simulate(stop), "Torskstopp (40 år)")

    summ(simulate(EcoParams(years=30, temp_delta=3.0, nutrient_load=1.8)),
         "Uppvärmning +3°C & övergödning")

    summ(simulate(EcoParams(years=30, salinity_delta=-2.0)), "Utsötning -2 PSU")

    summ(simulate(EcoParams(years=30, nutrient_load=0.5)), "Minskad övergödning")
