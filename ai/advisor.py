"""
AI-lager med Claude (kostnadseffektivt).

Två funktioner, som bara anropas vid användarklick (aldrig per bildruta):
  1. parse_scenario(text)  — fri svensk text → stress-parametrar (garanterad JSON)
  2. explain_result(...)   — sammanfattade resultat → kort svensk ekolog-förklaring

Vi använder Claude Haiku (billigast) och cachar den stora systemprompten med
prompt caching, så upprepade anrop blir ~90 % billigare. Nyckeln läses från miljön
(ANTHROPIC_API_KEY). Saknas nyckeln eller nätet degraderar vi snyggt.
"""

import json
import os

from . import reports

MODEL = "claude-haiku-4-5"   # billigast: $1/$5 per Mtok. Byt till claude-opus-4-8 för vassare svar.

# Systemprompt: modellens "kunskap" om Östersjön och reglagen. Cachas mellan anrop.
SYSTEM = """Du är en marinekolog specialiserad på Östersjöns ekosystem och hjälper till \
i en simuleringsapp. Du kan svenska.

Modellen delar Östersjön i sex zoner (Bottenviken, Bottenhavet, Finska viken, \
Egentliga Östersjön, Rigabukten, Öresund/Bälten) med en salthaltsgradient från nästan \
sött i norr (~3 PSU) till marint i söder (~18 PSU). Hela kretsloppet modelleras: \
näringssalter → växtplankton och cyanobakterier → djurplankton och bottenfauna (blåmussla) \
→ planktonätande fisk (sill, skarpsill, spigg) → kustrovfisk (abborre, gädda) och rovfisk \
(torsk, lax, havsöring) → toppredatorer (sjöfågel/skarv, gråsäl). När djuren dör blir de detritus/kadaver \
som nedbrytare omvandlar tillbaka till näring. Syret modelleras i två skikt: ytsyre och bottensyre.

Viktiga kända samband i Östersjön:
- Torsk behöver salt vatten (>~11 PSU) för att fortplanta sig; utsötning slår hårt mot torsk.
- När torsken kollapsar ökar skarpsill och spigg. Spiggen äter torskens, abborrens och gäddans \
  yngel och kan låsa fast ett 'spigghav' (wasp-waist-regimskifte) som är trögt att vända — \
  både i öppet hav (torsk) och i kustvikar (abborre/gädda).
- Abborre och gädda är kustrovfiskar i bräckt/sött vatten (norr, kustnära) och gynnas av utsötning.
- Lax och havsöring är laxfiskar som leker i åar/älvar men skiljer sig åt: laxen vandrar långt \
  ut i öppna havet och födosöker på sill/skarpsill, medan havsöringen är kustbunden och stationär \
  (stannar nära hemåns kust) och äter kustnära byten som spigg och ung sill.
- Bottenfauna (musslor) filtrerar plankton (näringsrening) men dör på syrefria bottnar.
- Övergödning + värme ger cyanobakterieblomning på sommaren och syrefria bottnar i djupa \
  bassänger (Egentliga Östersjön). Syrefria bottnar läcker fosfor (intern belastning) → ond cirkel.
- Varmare hav ger starkare skiktning → sämre bottensyre.

Stress-reglagen (parametrar):
- temp_delta: klimatuppvärmning i °C (baslinje 0)
- nutrient_load: näringsbelastning som multiplikator (1 = dagens, 2 = dubbel, 0.5 = halverad)
- salinity_delta: salthaltsändring i PSU (negativ = sötare hav)
- seal_hunt: extra säljakt (0 = fredad, >0 = jakt)
- bird_hunt: skyddsjakt/störning på sjöfågel/skarv (0 = fredad)
- noise: mellanårsvariation/väderbrus (0 = av, ~1 = tydlig variation)
- fishing: fisketryck (multiplikator) per art: sill, skarpsill, spigg, abborre, gadda, torsk. \
  0 = fiskestopp.
- years: hur många år simuleringen ska köra (5–100)"""

# JSON-schema som tvingar fram giltiga parametrar (structured output)
SCENARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "temp_delta": {"type": "number"},
        "nutrient_load": {"type": "number"},
        "salinity_delta": {"type": "number"},
        "seal_hunt": {"type": "number"},
        "bird_hunt": {"type": "number"},
        "noise": {"type": "number"},
        "fishing": {
            "type": "object",
            "properties": {
                "sill": {"type": "number"},
                "skarpsill": {"type": "number"},
                "spigg": {"type": "number"},
                "abborre": {"type": "number"},
                "gadda": {"type": "number"},
                "torsk": {"type": "number"},
            },
            "required": ["sill", "skarpsill", "spigg", "abborre", "gadda", "torsk"],
            "additionalProperties": False,
        },
        "years": {"type": "integer"},
        "motivering": {"type": "string"},
    },
    "required": ["temp_delta", "nutrient_load", "salinity_delta", "seal_hunt",
                 "bird_hunt", "noise", "fishing", "years", "motivering"],
    "additionalProperties": False,
}


_CLIENT = None  # återanvänds mellan anrop (skapa inte en ny klient varje gång)


def _client():
    """Returnerar en (cachad) Claude-klient, eller None om nyckel saknas."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        _CLIENT = anthropic.Anthropic(api_key=key)
    except Exception:
        _CLIENT = None
    return _CLIENT


# --- Svarscache på app-nivå --------------------------------------------------
# Identiska AI-förfrågningar återanvänds istället för att debiteras igen. Svaret
# blir detsamma, så det är korrekt. Nyckeln inkluderar rapport-kontexten, så att
# svaren uppdateras när användaren lägger till/tar bort underlag. (Detta är den
# verksamma cachningen här — Anthropics prompt-cache biter inte eftersom system-
# prompten är kortare än Haikus minsta cachebara längd på 2048 tokens.)
import hashlib

_RESP_CACHE = {}
_RESP_CACHE_MAX = 256


def _cache_key(*parts):
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    ctx = reports.reports_text() or ""
    return hashlib.sha1((raw + "\x00" + ctx).encode("utf-8")).hexdigest()


def _cache_get(key):
    return _RESP_CACHE.get(key)


def _cache_put(key, val):
    if len(_RESP_CACHE) >= _RESP_CACHE_MAX:
        _RESP_CACHE.pop(next(iter(_RESP_CACHE)))   # enkel FIFO-utrensning
    _RESP_CACHE[key] = val
    return val


def _system_blocks(with_reports=True):
    """
    Systemprompt med cache_control (cachas mellan anrop → billigare). Om användaren
    lagt in egna rapporter läggs de som ETT eget cachat block, så AI:n väger in dem.
    """
    blocks = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    if with_reports:
        rtext = reports.reports_text()
        if rtext:
            blocks.append({
                "type": "text",
                "text": ("Användaren har lagt in följande rapporter/underlag. Väg in dem "
                         "i dina svar och hänvisa till dem när de är relevanta:\n\n" + rtext),
                "cache_control": {"type": "ephemeral"},
            })
    return blocks


def parse_scenario(text, current=None):
    """
    Tolkar fri svensk text till stress-parametrar. Returnerar en dict med reglagen
    + 'motivering'. Faller tillbaka på baslinje om AI inte är tillgänglig.
    """
    base = {
        "temp_delta": 0.0, "nutrient_load": 1.0, "salinity_delta": 0.0,
        "seal_hunt": 0.0, "bird_hunt": 0.0, "noise": 0.0,
        "fishing": {"sill": 0.2, "skarpsill": 0.3, "spigg": 0.05,
                    "abborre": 0.1, "gadda": 0.1, "torsk": 0.2},
        "years": 30,
    }
    if current:
        base.update({k: current[k] for k in base if k in current})

    client = _client()
    if client is None:
        base["motivering"] = "AI ej tillgänglig (saknar API-nyckel) — använder baslinje."
        return base

    ckey = _cache_key("scenario", text, base)
    hit = _cache_get(ckey)
    if hit is not None:
        return hit

    prompt = (f"Nuvarande inställningar: {json.dumps(base, ensure_ascii=False)}\n\n"
              f"Användarens önskemål: \"{text}\"\n\n"
              "Uppdatera parametrarna så att de speglar önskemålet. Behåll värden som "
              "inte berörs. Skriv en kort svensk motivering (1–2 meningar) i 'motivering'.")
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=_system_blocks(),
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": SCENARIO_SCHEMA}},
        )
        text_out = next(b.text for b in resp.content if b.type == "text")
        return _cache_put(ckey, json.loads(text_out))
    except Exception as e:
        base["motivering"] = f"AI-fel ({type(e).__name__}) — använder baslinje."
        return base


def explain_result(summary):
    """
    Får en kompakt sammanfattning (start/slut-värden + reglage) och skriver en kort
    ekologisk förklaring på svenska. summary är en dict; håll den liten (kostnad).
    """
    client = _client()
    if client is None:
        return "AI ej tillgänglig — lägg en API-nyckel i .env för att få tolkningar."

    ckey = _cache_key("explain", summary)
    hit = _cache_get(ckey)
    if hit is not None:
        return hit

    prompt = (
        "Här är resultatet av en Östersjö-simulering (totala biomassor vid start och slut, "
        "samt inställningarna). Förklara kort och begripligt på svenska (3–5 meningar) vad "
        "som hände ekologiskt och varför, med koppling till kända mekanismer (regimskifte, "
        "cyanobakterieblomning, syrefria bottnar, torskens saltbehov). Undvik jargong.\n\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=_system_blocks(),
            messages=[{"role": "user", "content": prompt}],
        )
        return _cache_put(ckey, next(b.text for b in resp.content if b.type == "text").strip())
    except Exception as e:
        return f"Kunde inte hämta AI-förklaring ({type(e).__name__})."


def suggest_research(sensitivity, best=None):
    """
    Får känslighetsanalysen (vilka osäkra parametrar som styr utfallet mest) och
    föreslår VAR mer forskning behövs, på svenska. Väger in inlagda rapporter.
    """
    client = _client()
    if client is None:
        # Utan AI: räkna upp de känsligaste parametrarna som forskningsbehov.
        rows = "\n".join(f"- {s['namn']} (r={s['korrelation']}, {s['source']})"
                         for s in sensitivity[:5])
        return ("AI ej tillgänglig. Baserat på känslighetsanalysen bör forskning "
                "prioriteras där osäkerheten styr utfallet mest:\n" + rows)

    ckey = _cache_key("research", sensitivity, best)
    hit = _cache_get(ckey)
    if hit is not None:
        return hit

    prompt = (
        "Nedan är en känslighetsanalys från en Monte Carlo-körning av en Östersjö-modell. "
        "Korrelationen visar hur starkt varje osäker parameter styr det simulerade "
        "utfallet (ekosystemets hälsa). Hög |korrelation| = stor kunskapslucka som är "
        "dyr för besluten. Skriv på svenska en kort, prioriterad lista (3–5 punkter) över "
        "VAR mer forskning/övervakning bör göras och VARFÖR, kopplat till parametrarna och "
        "eventuella inlagda rapporter. Var konkret (mät vad, var, hur).\n\n"
        f"Känslighet: {json.dumps(sensitivity, ensure_ascii=False)}\n"
        f"Bästa strategi: {json.dumps(best, ensure_ascii=False) if best else 'okänd'}"
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=700,
            system=_system_blocks(),
            messages=[{"role": "user", "content": prompt}],
        )
        return _cache_put(ckey, next(b.text for b in resp.content if b.type == "text").strip())
    except Exception as e:
        return f"Kunde inte hämta forskningsförslag ({type(e).__name__})."


def suggest_reports(sensitivity=None):
    """
    Föreslår VILKA rapporter/studier användaren borde lägga in som underlag, så att
    simuleringen blir bättre förankrad. Väger in redan inlagda rapporter (för att
    inte föreslå dubbletter). Returnerar en kort svensk lista.
    """
    client = _client()
    have = reports.list_reports()
    have_titles = ", ".join(r["titel"] for r in have) or "inga ännu"
    if client is None:
        return ("AI ej tillgänglig. Klassiska underlag att lägga in: HELCOM State of the "
                "Baltic Sea, ICES WGBFAS (torsk/sill/skarpsill), Conley et al. 2009 (hypoxi), "
                "Casini et al. (regimskifte), Eklöf/Bergström (spigg vs abborre/gädda).")
    ckey = _cache_key("suggest_reports", sensitivity, have_titles)
    hit = _cache_get(ckey)
    if hit is not None:
        return hit

    prompt = (
        "Föreslå på svenska 4–6 konkreta rapporter/dataset/studier som skulle förbättra "
        "den här Östersjö-simuleringens förankring — särskilt kring de största "
        "osäkerheterna. För varje: titel/källa och en rad om VAD den bidrar med och VILKEN "
        "parameter den skulle hjälpa att kalibrera. Föreslå INTE sådant som redan är inlagt.\n\n"
        f"Redan inlagda rapporter: {have_titles}\n"
        f"Känslighetsanalys (om finns): {json.dumps(sensitivity, ensure_ascii=False) if sensitivity else 'saknas'}"
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=700, system=_system_blocks(),
            messages=[{"role": "user", "content": prompt}],
        )
        return _cache_put(ckey, next(b.text for b in resp.content if b.type == "text").strip())
    except Exception as e:
        return f"Kunde inte hämta rapportförslag ({type(e).__name__})."


# Målgruppsanpassade instruktioner för rapporttexten (export-lägen).
REPORT_MODE_PROMPTS = {
    "nyfiken": (
        "Skriv för en NYFIKEN ALLMÄNHET utan förkunskaper. Var mycket enkel, kort och "
        "konkret (rubriker + 3–4 korta stycken). Undvik fackspråk; förklara det viktigaste "
        "med vardagsord och gärna en liknelse. Ta upp: hur mår havet, vad hände i körningen, "
        "och varför det spelar roll för oss människor. Väck nyfikenhet."),
    "generell": (
        "Skriv en kort, professionell och saklig rapport (rubriker + 4–6 stycken). Ta upp: "
        "utgångsläge, vald strategi och dess effekt på ekosystemets hälsa (10/20/50/100 år om "
        "det finns), nationalekonomiskt värde, samt var mer forskning behövs. Koppla till kända "
        "mekanismer."),
    "politik": (
        "Skriv ett BESLUTSUNDERLAG för politiker och beslutsfattare (rubriker + 5–7 stycken). "
        "Fokusera på: politiska strategier och handlingsalternativ, argument för och emot, "
        "utvecklings- och investeringsfrågor, samhällsnytta och kostnaden för att inte agera. "
        "Lyft de ekonomiska värdena tydligt och nämn att de redovisas i både euro och lokal "
        "valuta per land. Var konkret, balanserad och handlingsorienterad; undvik övertolkning."),
    "forskare": (
        "Skriv för FORSKARE och sakkunniga (rubriker + 5–7 stycken). Gå djupare på mekanismer "
        "och samband i näringsväven, återkopplingar och regimskiften. Var extra tydlig med "
        "OSÄKERHETER och var forskningen är oense eller har kunskapsluckor (utifrån "
        "känslighetsanalysen). Avsluta med konkreta NÄSTA STEG: vilka studier/mätningar som "
        "skulle minska osäkerheten mest, i prioritetsordning. Koppla till litteraturen."),
}


def report_text(summary, lang_name="svenska", mode="generell"):
    """
    Skriver en sammanhängande rapporttext (för export) av en simulering/MC-sammanfattning,
    på valt språk och anpassad efter målgrupp (mode). Faller tillbaka utan AI.
    """
    client = _client()
    if client is None:
        return None
    mode = mode if mode in REPORT_MODE_PROMPTS else "generell"
    ckey = _cache_key("report_text", lang_name, mode, summary)
    hit = _cache_get(ckey)
    if hit is not None:
        return hit
    prompt = (
        f"Skriv på {lang_name}. {REPORT_MODE_PROMPTS[mode]}\n\n"
        f"Underlag (JSON):\n{json.dumps(summary, ensure_ascii=False)[:6000]}"
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1400, system=_system_blocks(with_reports=True),
            messages=[{"role": "user", "content": prompt}],
        )
        return _cache_put(ckey, next(b.text for b in resp.content if b.type == "text").strip())
    except Exception:
        return None


def _translate_batch(client, strings, lang_name, lang_code):
    """Översätter EN batch nycklar. Returnerar dict eller None vid fel."""
    schema = {
        "type": "object",
        "properties": {k: {"type": "string"} for k in strings},
        "required": list(strings.keys()),
        "additionalProperties": False,
    }
    prompt = (
        f"Översätt värdena i följande JSON från svenska till {lang_name} ({lang_code}). "
        "Behåll nycklarna oförändrade. Det är UI-text i en Östersjö-simulering; håll det "
        "kort och naturligt. Behåll siffror/enheter/emoji.\n\n"
        f"{json.dumps(strings, ensure_ascii=False)}"
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=4000,
            system=[{"type": "text", "text": "Du är en professionell översättare."}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        return json.loads(next(b.text for b in resp.content if b.type == "text"))
    except Exception:
        return None


def translate_table(strings, lang_name, lang_code, batch=25):
    """
    Översätter en dict {nyckel: svensk_text} till målspråket, i BATCHAR (annars
    spränger den långa tabellen token-taket). Returnerar {nyckel: översättning}
    eller None om AI saknas / alla batchar misslyckas.
    """
    client = _client()
    if client is None:
        return None
    keys = list(strings.keys())
    out = {}
    for i in range(0, len(keys), batch):
        chunk = {k: strings[k] for k in keys[i:i + batch]}
        res = _translate_batch(client, chunk, lang_name, lang_code)
        if res:
            out.update(res)
    return out or None
