"""
Arter (kompartment) i näringskedjan och deras parametrar.

Modellen är en förenklad NPZD-modell (Nutrients–Phytoplankton–Zooplankton–Detritus)
utökad med fisk och säl. Varje zon har ETT exemplar av varje kompartment nedan.
Biomassor och näring är i relativa enheter (mg/m³-storleksordning), hastigheter per år.

Parametrarna är litteraturförankrade riktvärden, kalibrerade för att ge stabil baslinje
och rimliga stress-svar (se data/params.json för källor). De är INTE exakta mätvärden.
"""

import numpy as np

# Ordning i tillståndsvektorn (per zon). Index 0..11.
# Syret delas i två skikt (ytvatten och bottenvatten) för att fånga hur
# Östersjöns djupa bassänger blir syrefria på botten medan ytan är syrerik.
COMPARTMENTS = [
    "N",          # 0  löst näring (begränsande näringsämne)
    "phyto",      # 1  växtplankton
    "cyano",      # 2  cyanobakterier (kvävefixerande sommarblomning)
    "zoo",        # 3  djurplankton
    "bentos",     # 4  bottenfauna (blåmussla m.fl.) — filtrerare, syrekänslig
    "sill",       # 5  sill
    "skarpsill",  # 6  skarpsill
    "spigg",      # 7  storspigg
    "abborre",    # 8  abborre (kustrovfisk, brackvatten)
    "gadda",      # 9  gädda (kustrovfisk, brackvatten)
    "torsk",      # 10 torsk (rovfisk, öppet hav)
    "lax",        # 11 lax (pelagisk rovfisk, leker i älvar)
    "fagel",      # 12 sjöfågel (skarv, ejder m.fl.) — toppredator
    "sal",        # 13 gråsäl — toppredator
    "O2",         # 14 ytsyre
    "O2b",        # 15 bottensyre (under språngskiktet)
    "det",        # 16 detritus/kadaver (dött organiskt material — kretsloppets slut→start)
]
CI = {name: i for i, name in enumerate(COMPARTMENTS)}
N_COMP = len(COMPARTMENTS)

# Svenska visningsnamn för webben
DISPLAY = {
    "N": "Näring", "phyto": "Växtplankton", "cyano": "Cyanobakterier",
    "zoo": "Djurplankton", "bentos": "Bottenfauna", "sill": "Sill",
    "skarpsill": "Skarpsill", "spigg": "Spigg", "abborre": "Abborre",
    "gadda": "Gädda", "torsk": "Torsk", "lax": "Lax", "fagel": "Sjöfågel",
    "sal": "Säl", "O2": "Ytsyre", "O2b": "Bottensyre", "det": "Detritus/kadaver",
}

# Enheter för y-axeln i graferna. SI-enheter, konsekvent som i hela-ekosystem-
# massbalansmodeller (Ecopath): all levande biomassa i g/m² (= ton/km²), löst
# näring i mg/m³, syre i % mättnad (0 = syrefritt/dött, ~100 = mättat, >100 =
# övermättnad vid algblomning). OBS: de absoluta talen är modellindex i denna
# storleksordning — inte uppmätta beståndsuppskattningar.
UNIT = {
    "N": "mg/m³", "phyto": "g/m²",
    "cyano": "g/m²", "zoo": "g/m²",
    "bentos": "g/m²",
    "sill": "g/m²", "skarpsill": "g/m²", "spigg": "g/m²",
    "abborre": "g/m²", "gadda": "g/m²",
    "torsk": "g/m²", "lax": "g/m²",
    "fagel": "g/m²", "sal": "g/m²",
    "O2": "% mättnad", "O2b": "% mättnad", "det": "g/m²",
}

# --- Planktondynamik ---------------------------------------------------------
# Växtplankton och cyanobakterier har var sin takkapacitet (självskuggning) så att
# de kan blomma i olika säsonger: växtplankton på våren, cyanobakterier på sommaren.
PHYTO_CAP = 30.0    # takkapacitet växtplankton
CYANO_CAP = 15.0    # takkapacitet cyanobakterier
MU_PHYTO = 35.0     # max tillväxthastighet växtplankton (per år)
K_N = 2.5           # halvmättnad näringsupptag (Monod) — N-begränsas på sommaren
M_PHYTO = 5.0       # dödlighet/sedimentation växtplankton

MU_CYANO = 30.0     # cyanobakterier: blommar på sommaren, fixerar eget kväve
K_N_CYANO = 2.5     # klarar sig sämre på löst näring (men behöver ej mycket)
M_CYANO = 4.0
CYANO_TEMP_MIN = 15.0   # blommar först när ytvattnet är varmt (sommar)
CYANO_FIX = 0.22        # hur mycket kvävefixering ersätter näringsbrist (0–1)
CYANO_GRAZE = 0.1       # djurplankton äter ogärna (giftiga) cyanobakterier

# Liten invandring/återkolonisering (från floder, refugier) så att en art aldrig
# blir permanent utdöd utan kan återhämta sig när förhållandena förbättras.
IMMIG = 0.01

# --- Djurplankton ------------------------------------------------------------
G_ZOO = 22.0        # betningshastighet på plankton
K_PREY_ZOO = 3.0    # halvmättnad (Holling II)
ASSIM_ZOO = 0.6     # assimilationseffektivitet
M_ZOO = 4.0         # dödlighet + respiration
QUAD_ZOO = 0.05     # täthetsberoende dödlighet (closure) — dämpar boom-bust-toppar

# --- Bottenfauna (bentos: blåmussla, östersjömussla, märlkräftor) ------------
# Filtrerar växtplankton och detritus ur vattnet (viktig näringsrening!) och är
# mat åt bottenätande fisk och dykänder. MYCKET syrekänslig — dör på döda bottnar,
# vilket gör den till en tydlig indikator på övergödningens bottenskador.
BENTOS_FILTER = 4.5     # filtreringshastighet på plankton+detritus
BENTOS_KHALF = 12.0     # halvmättnad
BENTOS_ASSIM = 0.32     # assimilationseffektivitet
BENTOS_MORT = 0.75      # naturlig dödlighet
BENTOS_BRAKE = 0.06     # täthetsberoende bromsning (håller bentos på rimlig nivå)
BENTOS_HYP = 3.0        # extra dödlighet vid syrebrist (styrs av bottensyret)

# --- Fisk (planktonätare + rovfisk) och säl ----------------------------------
# Varje art: max konsumtion, halvmättnad, effektivitet, naturlig dödlighet,
# samt salthaltspreferens (optimum + bredd) som styr nord–syd-utbredningen.
# Effektivitet/dödlighet balanserade så att arterna kan leva vid baslinjen.
FISH = {
    # Sill dominerar i norra/centrala, brackvattnet; skarpsill i det saltare södra.
    "sill": dict(cons=6.8, khalf=5.0, eff=0.48, mort=0.35,
                 sal_opt=5.0, sal_width=5.0),
    "skarpsill": dict(cons=6.8, khalf=5.0, eff=0.48, mort=0.38,
                      sal_opt=9.0, sal_width=5.0),
    # Spigg är svagare konkurrent MEN tål bredast salthaltsspann → gynnas i norr
    # och tar över när torsken (dess predator) försvinner.
    "spigg": dict(cons=5.5, khalf=5.0, eff=0.38, mort=0.50,
                  sal_opt=6.0, sal_width=9.0),
    # Kustrovfiskar: abborre och gädda är torskens motsvarighet i det bräckta
    # kustvattnet i norr. De trivs i låg salthalt (sötvattenarter) och håller nere
    # spiggen — men spiggen äter DERAS yngel (samma wasp-waist-fälla som för torsk).
    "abborre": dict(cons=6.5, khalf=4.5, eff=0.46, mort=0.35,
                    sal_opt=3.5, sal_width=4.5),
    "gadda": dict(cons=5.0, khalf=6.0, eff=0.46, mort=0.28,
                  sal_opt=3.0, sal_width=4.5),
    "torsk": dict(cons=6.0, khalf=8.0, eff=0.50, mort=0.25,
                  sal_opt=12.0, sal_width=5.0),  # kräver marint vatten
    # Lax: pelagisk rovfisk som jagar sill/skarpsill i öppet hav och leker i älvar
    # (norr). Lågt bestånd, högt värde. Bred salthaltstolerans.
    "lax": dict(cons=5.0, khalf=7.0, eff=0.12, mort=0.30,
                sal_opt=6.0, sal_width=9.0),
    # Sjöfågel (skarv, ejder, tärna m.fl.): äter kustfisk och bottenfauna.
    "fagel": dict(cons=2.4, khalf=6.0, eff=0.10, mort=0.22,
                  sal_opt=8.0, sal_width=20.0),  # finns längs hela kusten
    "sal": dict(cons=2.0, khalf=18.0, eff=0.14, mort=0.10,
                sal_opt=8.0, sal_width=20.0),    # rör sig överallt
}

# Näringsväv: predator → {byte: preferens}. Preferensen viktar vem som äts mest.
# Näringsväv: predator → {byte: preferens}. Används för pyramidens/nätverkets
# pilar i webben (och som dokumentation). Kretsloppet sluts av att ALLA dör →
# detritus/kadaver → nedbrytare → näring igen.
DIET = {
    "zoo":       {"phyto": 1.0, "cyano": 0.3},          # cyanobakterier äts ogärna
    "bentos":    {"phyto": 0.7, "det": 1.0},            # filtrerar plankton + detritus
    "sill":      {"zoo": 1.0},
    "skarpsill": {"zoo": 1.0},
    "spigg":     {"zoo": 1.0},
    "abborre":   {"zoo": 0.4, "spigg": 0.7, "skarpsill": 0.2},  # kustrovfisk
    "gadda":     {"spigg": 0.6, "abborre": 0.5, "sill": 0.3},   # topp i kustkedjan
    "torsk":     {"sill": 0.9, "skarpsill": 1.0, "spigg": 0.6, "bentos": 0.4},
    "lax":       {"sill": 0.8, "skarpsill": 0.6, "spigg": 0.3},   # pelagisk jägare
    "fagel":     {"spigg": 0.7, "abborre": 0.5, "sill": 0.4, "bentos": 0.6},
    "sal":       {"sill": 0.6, "torsk": 1.0, "skarpsill": 0.4, "lax": 0.5},
    "det":       {},   # detritus/kadaver: slutstation som bryts ned till näring
}

# "Wasp-waist": spiggen äter torskens (och abborrens) yngel och håller nere
# torskens återhämtning även efter att fisket minskat. Styrkan på denna
# larvpredation — ett litteraturbelagt fenomen i Egentliga Östersjön.
SPIGG_LARVAL_PREDATION = 0.7

# Samma mekanism vid kusten: spiggen äter abborrens och gäddans yngel och kan
# låsa fast ett "spigghav" i grunda vikar, där kustrovfisken slås ut.
# (Eklöf et al. 2020; Bergström et al. 2019 — dokumenterat på svenska ostkusten.)
SPIGG_COASTAL_PREDATION = 0.6

# Sjöfågeln (skarv m.fl.) är nu en egen art (kompartment "fagel"). Reglaget
# "bird_hunt" fungerar som skyddsjakt/störning — extra dödlighet på fågeln,
# analogt med säljakt (0 = fredad).

# --- Syre och detritus -------------------------------------------------------
O2_PROD = 0.15      # syreproduktion per enhet primärproduktion (i ytan)
O2_REAER = 60.0     # syresättning av ytan från atmosfären mot mättnad (per år)
                    # högt: ytvattnet håller sig nära mättnad, som i verkligheten
O2_SAT = 100.0      # mättnadsnivå (relativ, ~ % mättnad)
DECOMP = 5.0        # nedbrytning av detritus → näring (förbrukar syre)
O2_PER_DECOMP = 0.8 # syreåtgång per nedbruten detritus
DEEP_FACTOR = 1.8   # djupa bassänger: mer detritus samlas på botten

# Kväve-sänkor: utan dessa skulle näringen bara ackumulera. Denitrifikation +
# utflöde till Nordsjön tar bort löst näring; en del detritus begravs permanent i
# sedimentet. Det håller näringsbudgeten sluten och realistisk.
N_LOSS = 0.30       # denitrifikation + utflöde (per år) — sänka för löst näring
DET_BURIAL = 0.10   # permanent begravning av detritus i sedimentet (per år)

# --- Vertikal syresättning: yt- vs bottenvatten ------------------------------
# Bottenvattnet får ENDAST syre via vertikal blandning från ytan (ingen kontakt
# med atmosfären). Blandningen bromsas av skiktning (språngskikt/halinklin), som
# är stark i djupa bassänger och förstärks när ytvattnet blir varmare. Därför blir
# djupa, varma, övergödda bassänger syrefria på botten — som i Egentliga Östersjön.
VEXCH_MAX = 24.0    # max vertikalt syreutbyte yta↔botten (per år)
STRAT_DEEP = 12.0   # extra skiktning i djupa bassänger (starkt språngskikt)
STRAT_TEMP = 0.35   # varmare ytvatten → starkare skiktning → sämre bottensyre
SURF_LOSS = 0.10    # bottenvattnet är en liten volym → ventilationen dränerar ytan lite
INTERNAL_LOAD = 4.0  # intern näringsbelastning: syrefria bottnar läcker fosfor
ANOX_THRESH = 15.0  # bottensyre under detta ≈ syrefri, död botten

# --- Temperaturberoende (Q10) ------------------------------------------------
Q10 = 2.0           # biologiska hastigheter ~fördubblas per +10 °C
T_REF = 10.0        # referenstemperatur


def q10_factor(temp):
    """Temperaturfaktor för biologiska hastigheter (Q10-regeln)."""
    return Q10 ** ((temp - T_REF) / 10.0)


def salinity_response(species, salinity):
    """
    Hur väl en art trivs vid en given salthalt (0–1, klockkurva runt optimum).
    Ger nord–syd-gradienten: torsk trivs bara i söder, spigg/sill överallt.
    """
    p = FISH[species]
    return float(np.exp(-((salinity - p["sal_opt"]) ** 2) / (2 * p["sal_width"] ** 2)))


def cod_reproduction_factor(salinity):
    """
    Torskrekrytering kräver tillräcklig salthalt — torskägg måste flyta i
    'reproduktionsvolymen' (behöver ~>11 PSU). Under det blir rekryteringen dålig.
    Mjuk tröskel mellan ~7 och 13 PSU.
    """
    return float(1.0 / (1.0 + np.exp(-(salinity - 10.0) * 1.2)))
