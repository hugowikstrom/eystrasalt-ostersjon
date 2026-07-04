# 🌊 Eystrasalt — en digital tvilling för Östersjön

Eystrasalt är en **öppen, pedagogisk ekosystemsimulering av Östersjön** — hela
kretsloppet från näringssalter till toppredatorer och tillbaka igen. Målet är att
**skapa förståelse**, samla ihop kunskap på ett ställe och göra ekologiska
simuleringar förankrade i känd litteratur och forskning.

Du kan skruva på klimat, övergödning, salthalt och fiske, se hur hela näringsväven
svarar, jämföra förvaltningsstrategier under osäkerhet (Monte Carlo), räkna ut vad ett
friskare hav är värt för de angränsande länderna, och exportera resultatet som sida,
PowerPoint eller rapport — på alla Östersjöspråk + engelska.

## Om projektet — och en ärlig brasklapp

Jag som byggt det här är en **glad amatör med ett stort hjärta för Östersjön** och för
jordens välmående i stort. Jag är ingen havsforskare. **Koden är genererad tillsammans
med Claude (AI).** Det betyder att det med säkerhet finns **förbättringar att göra och
fel i beräkningsmodeller, parametrar och data.** Modellen är en *rimlig, litteratur­förankrad
förenkling* — inte en forskningsvaliderad prognosmodell.

Därför är detta **open source**. Ladda ned det, granska det, håll inte med, gör det bättre.
Har du kunskap, data, en rättelse eller en önskan — hör av dig eller skicka en idé via
appens **Idélåda**. Tillsammans kan vi förfina en riktigt bra digital tvilling för vårt
innanhav. 💙

**Kontakt:** hugo@bigakwa.com

## Vad modellen innehåller

- **17 kompartment** i näringsväven: näringssalter, växtplankton, cyanobakterier,
  djurplankton, bottenfauna (blåmussla), sill, skarpsill, spigg, abborre, gädda, torsk,
  lax, sjöfågel/skarv, gråsäl, ytsyre, bottensyre och detritus/kadaver.
- **6 zoner** med salthaltsgradient (Bottenviken → Öresund/Bälten) som utbyter vatten.
- **Kretsloppet sluts**: allt som dör blir detritus/kadaver som bryts ned till näring igen.
- Kända Östersjö-mekanismer: torskens saltbehov, wasp-waist-regimskiftet (spiggen som
  slår ut torsk-, abborr- och gäddyngel), cyanobakterieblomning, syrefria bottnar och
  intern fosforbelastning, klimatuppvärmningens effekt på skiktning och syre.
- **Verifiering mot litteraturen** (8 kontroller med källhänvisning) och en inbyggd
  känslighetsanalys som pekar ut var mer forskning behövs.
- **AI-lager (Claude Haiku)** för att tolka scenarier i fritext, förklara resultat,
  föreslå forskning/rapporter och översätta gränssnittet.

Referensbiblioteket i `data/reports/` bygger på HELCOM, ICES, SMHI, Havs- och
vattenmyndigheten m.fl. (egna sammanfattningar, inte upphovsrättsskyddad fulltext).

## Kör lokalt

```bash
git clone <detta-repo> balticsea && cd balticsea
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py           # → http://localhost:5800
```

**AI-funktionerna är valfria.** Simuleringen, graferna, Monte Carlo, ekonomin och
verifieringen fungerar helt utan nyckel. Vill du ha AI:n (tolka scenarier i fritext,
förklara resultat, föreslå forskning, översätta gränssnittet) — lägg in din **egen**
Anthropic-nyckel:

```bash
cp .env.example .env    # fyll sedan i ANTHROPIC_API_KEY=din-egen-nyckel
```

Inga lösenord eller nycklar ligger i koden — `.env` är i `.gitignore` och checkas
aldrig in. Var och en som kör projektet använder sin egen (valfria) nyckel.

### Köra för många samtidiga användare

Flasks inbyggda server räcker för test. För en publik instans, kör med en
produktionsserver (fler arbetare = fler samtidiga besökare):

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5800 app:app
```

Lägg gärna en omvänd proxy (t.ex. Caddy eller nginx) framför för HTTPS.

Testa modellen fristående:

```bash
python -m model.ecosystem      # självtest: baslinje + scenarier
python -m model.verification   # kontroller mot litteraturen
python -m ai.seed_reports      # läser in referensbiblioteket
```

## Struktur

```
model/   ekosystemets ekvationer (ecosystem.py), arter (species.py),
         zoner, hälsoindex, ekonomi, Monte Carlo, verifiering
ai/      Claude-lager: scenariotolk, förklaring, forskning, export, i18n, lagring
web/     gränssnittet (vanilla JS + SVG, inga tunga ramverk)
data/    hjälptexter, språk, rapporter, sparade körningar, idéer
```

## Bidra

Idéer, rättelser, bättre parametrar/data och nya arter är mycket välkomna — via
pull request, issue, appens Idélåda, eller mejl till hugo@bigakwa.com.

## Licens

Open source (MIT). Använd fritt, bidra gärna. Ingen garanti — se brasklappen ovan.

---

*"Ett friskare hav är värt mer än vi tror — och förståelse är första steget."*
