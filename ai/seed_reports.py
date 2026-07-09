"""
Seed-bibliotek: centrala myndighets- och forskningskällor om Östersjön.

Vi kan inte ladda ned all fulltext (upphovsrätt + mängd), så här ligger KURERADE,
egenformulerade sammanfattningar av nyckelkällorna med referens. De läses in i
rapport-lagret (data/reports/) så att AI:n väger in dem. Lägg gärna till mer
fulltext själv via Rapporter-fliken.

Kör:  python -m ai.seed_reports        (lägger till dem som inte redan finns)
"""

from . import reports

LIBRARY = [
    ("HELCOM (2023) State of the Baltic Sea – Third holistic assessment (HOLAS 3)",
     "HELCOM:s samlade bedömning: övergödning är fortsatt det största problemet; stora "
     "delar av öppna Östersjön uppnår inte god miljöstatus. Rekordstora syrefria bottnar "
     "i Egentliga Östersjön. Torsken i dålig kondition. Betonar att intern fosforbelastning "
     "från syrefria bottnar fördröjer återhämtning trots minskad extern tillförsel."),
    ("HELCOM Baltic Sea Action Plan (BSAP, uppdaterad 2021)",
     "Åtgärdsplan med maximala tillåtna näringstillförslar (MAI) per bassäng och land. "
     "Mål om god status till 2030. Fastställer landvisa nedskärningar av kväve och fosfor "
     "som underlag för scenariot 'minskad övergödning'."),
    ("ICES (årlig) WGBFAS – Baltic Fisheries Assessment Working Group",
     "ICES beståndsuppskattningar och fångstråd för torsk, sill/strömming och skarpsill. "
     "Östlig torsk är kollapsad (fiskestopp sedan 2019); rekrytering och kondition historiskt "
     "låg. Underlag för fiskeparametrar och referensnivåer (F, SSB)."),
    ("Conley et al. (2009) Hypoxia-related processes in the Baltic Sea. Env. Sci. Technol.",
     "Visar kopplingen övergödning → syrefria bottnar och den interna fosforåterföringen "
     "(bottnar läcker fosfor vid syrebrist), en självförstärkande ond cirkel. Central för "
     "parametern intern belastning (INTERNAL_LOAD)."),
    ("Carstensen et al. (2014) Deoxygenation of the Baltic Sea during the last century. PNAS",
     "Dokumenterar tiofaldig ökning av hypoxisk bottenareal under 1900-talet, drivet av "
     "både näringstillförsel och uppvärmning/skiktning. Stöd för temperaturens effekt på "
     "bottensyret (STRAT_TEMP)."),
    ("Casini et al. (2009) Trophic cascades promote threshold-like shifts. PNAS",
     "Torskkollapsen i Egentliga Östersjön utlöste ett regimskifte: skarpsill ökade, "
     "vilket kaskaderade nedåt i näringsväven. Stöd för wasp-waist-dynamiken."),
    ("Casini et al. (2016) Hypoxic areas, density-dependence and food limitation for cod.",
     "Kopplar torskens dåliga kondition till syrefria bottnar (mindre bottendjur/habitat) "
     "och tät-beroende födobrist. Underlag för torskens hypoxikänslighet (HYP_MORT_TORSK)."),
    ("Eklöf et al. (2020) A spatial regime shift from predator to prey dominance. Communications Biology",
     "Storspiggen har ökat kraftigt längs svenska kusten och skapar ett 'spigghav' där den "
     "äter yngel av abborre och gädda — ett rumsligt regimskifte i kustzonen. Central för "
     "spiggens larvpredation på kustrovfisk (SPIGG_COASTAL_PREDATION)."),
    ("Bergström et al. (2019) Long-term decline of coastal predatory fish. Baltic coastal ecosystems",
     "Långsiktig nedgång för abborre och gädda i delar av kustzonen, kopplad till spigg, "
     "övergödning och habitatförändringar. Stöd för kustrovfisk-dynamiken."),
    ("Kahru & Elmgren (2014) Multidecadal time series of cyanobacterial blooms. Biogeosciences",
     "Satellitserie över cyanobakterieblomningar; blomningarna gynnas av varmt, skiktat och "
     "fosforrikt vatten. Underlag för cyanobakteriernas blomningsbenägenhet (CYANO_FIX)."),
    ("Gustafsson et al. (2012) Reconstructing the development of Baltic hypoxia (BALTSEM). Ambio",
     "Modellstudie (BALTSEM) över hypoxins utveckling och åtgärders tröghet pga intern "
     "belastning. Referens för att bottensyret svarar långsamt på minskad övergödning."),
    ("MacKenzie et al. (2007) Impact of climate change on Baltic cod recruitment.",
     "Torskrekryteringen kräver tillräcklig salthalt och syre i 'reproduktionsvolymen'; "
     "utsötning och syrebrist krymper den. Underlag för torskens salt-/lekberoende."),
    ("Mohrholz et al. (2015) Fresh oxygen for the Baltic Sea — the 2014 Major Baltic Inflow. J. Marine Systems",
     "Stora saltvatteninflöden (MBI) ventilerar tillfälligt djupvattnet med syre men är "
     "oregelbundna. Underlag för ventilationsparametern (VEXCH_MAX) och dess osäkerhet."),
    ("Reusch et al. (2018) The Baltic Sea as a time machine for the future coastal ocean. Science Advances",
     "Översikt: Östersjön som modellhav för klimat/övergödning; sammanfattar kumulativa "
     "stressorer och regimskiften. Bra helhetsram för simuleringens antaganden."),
    ("SMHI – Syrekartläggning och oceanografiska tidsserier (löpande)",
     "Svenska SMHI:s mätningar av syrehalt, temperatur och salthalt i Östersjöns bassänger. "
     "Empiriskt underlag för bottensyre, skiktning och ytsyre i modellen."),
    ("Havs- och vattenmyndigheten – Ekosystembaserad förvaltning av fisk och kust",
     "Svensk myndighetsvägledning om förvaltning av kustfiskbestånd (abborre, gädda), "
     "spiggproblematiken och åtgärder i kustzonen. Underlag för kust- och förvaltningsscenarier."),
    ("Andersen et al. (2017) Long-term temporal and spatial trends in eutrophication status of the Baltic Sea. Biological Reviews",
     "Syntes av övergödningsstatus 1901–2012: näringstillförseln kulminerade på 1980-talet och "
     "har därefter minskat, men havet svarar långsamt pga intern belastning och tröga bottnar. "
     "Underlag för trögheten i återhämtning vid minskad näringstillförsel."),
    ("Bergström et al. (2015) Stickleback increase in the Baltic Sea. Marine Ecology Progress Series",
     "Dokumenterar storspiggens kraftiga ökning och dess roll i regimskiften i kustzonen; spiggen "
     "gynnas av utslagen kustrovfisk och varmare vatten. Stöd för wasp-waist-mekaniken i kust."),
    ("Vahtera et al. (2007) Internal ecosystem feedbacks enhance nitrogen-fixing cyanobacteria blooms. Ambio",
     "Beskriver den självförstärkande kopplingen: syrefria bottnar → fosforläckage → "
     "cyanobakterieblomning (kvävefixering) → mer organiskt material → mer syrebrist. Central "
     "för intern belastning och cyanobakteriernas näringsdynamik."),
    ("Elmgren et al. (2015) Baltic Sea management: successes and failures. Ambio",
     "Utvärderar decennier av Östersjöförvaltning; visar att åtgärder mot övergödning fungerar "
     "men kräver uthållighet, och att fiskeförvaltning och övergödning måste ses ihop."),
    ("Bryhn et al. (2022) Grey seal and cormorant interactions with Baltic coastal fish. SLU Aqua",
     "Svensk sammanställning om gråsäl och skarv som predatorer på kustfisk och deras samspel "
     "med fisket. Underlag för toppredatorernas (säl, sjöfågel) tryck på fiskbestånden."),
    ("Hansson et al. (2018) Competition for the fish – shared fishery resources in the Baltic. ICES J. Marine Science",
     "Analyserar konkurrensen om fiskresurserna mellan säl, skarv och yrkesfiske; kvantifierar "
     "toppredatorernas konsumtion relativt fångsterna. Stöd för predationsparametrarna."),
    ("Ojaveer et al. (2010) Status of biodiversity in the Baltic Sea. PLoS ONE",
     "Översikt av Östersjöns biologiska mångfald: låg artrikedom pga bräckt vatten gör "
     "ekosystemet känsligt — enskilda arter (t.ex. torsk, spigg) har stor systempåverkan. "
     "Motiverar varför regimskiften slår hårt i just Östersjön."),
    ("Snoeijs-Leijonmalm & Andrén (2017) Why is the Baltic Sea so special? (i Biological Oceanography of the Baltic Sea)",
     "Läroboksöversikt av Östersjöns särdrag: ung, bräckt, skiktad och artfattig, med stark "
     "salthaltsgradient. Ramverk för zonernas salthaltsberoende och artutbredning i modellen."),
    ("Reusch et al. / BONUS & HELCOM – Nutrient load reduction scenarios (BSAP-underlag)",
     "Scenariounderlag för hur olika nivåer av kväve- och fosforminskning påverkar status per "
     "bassäng. Stöd för näringsreglaget och 'minskad övergödning'-scenariot."),
    ("Östman et al. (2016) Top-down control as important as nutrient loading. J. Applied Ecology",
     "Visar att BÅDE övergödning och förlust av rovfisk (gädda, abborre) driver ökningen av "
     "karpfisk (mört m.fl.), storspigg och trådalger i Östersjöns kustvikar — top-down och "
     "bottom-up samverkar. Underlag för karpfiskens (mört) dynamik i modellen."),
    ("Florin, Sundblad & ICES – Skrubbskädda/flundra i Östersjön",
     "Skrubbskädda/flundra är Östersjöns vanligaste plattfisk: bottenlevande, betar bottenfauna "
     "(musslor, kräftdjur) och påverkas av salthalt och syrefria bottnar. Underlag för "
     "plattfiskens roll som länk mellan bottendjur och rovfisk/säl."),
]


def seed():
    """Lägger till referenser som inte redan finns (matchar på titel). Returnerar antal tillagda."""
    have = {r["titel"] for r in reports.list_reports()}
    added = 0
    for titel, text in LIBRARY:
        if titel in have:
            continue
        reports.add_report(titel, text)
        added += 1
    return added


if __name__ == "__main__":
    n = seed()
    print(f"Seedade {n} referenser. Totalt {len(reports.list_reports())} rapporter i biblioteket.")
