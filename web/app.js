"use strict";

// ---- Tillstånd ----
let DEF = null;        // /api/defaults
let RES = null;        // senaste simuleringsresultat
let MC = null;         // senaste Monte Carlo-resultat
let STR = {};          // aktuell språktabell (i18n)
let ti = 0;            // aktuellt tidsindex
let selectedZone = "egentliga";
let selectedSeries = new Set(["sill", "torsk", "abborre", "gadda"]);
let playing = false;
let rafId = null;
let currentUser = localStorage.getItem("eystra_user") || "";

const ADJ = [
  ["bottenviken","bottenhavet"],["bottenhavet","egentliga"],
  ["egentliga","finska"],["egentliga","riga"],["egentliga","sunden"],
];

const LAYERS = [
  { key: "pie",   label: "Tårtdiagram (biomassa)", type: "pie" },
  { key: "status", label: "Bottenstatus", type: "status" },
  { key: "O2b",   label: "Bottensyre",    type: "cont", cmap: "oxy" },
  { key: "O2",    label: "Ytsyre",        type: "cont", cmap: "oxy" },
  { key: "phyto", label: "Växtplankton",  type: "cont", cmap: "bio" },
  { key: "cyano", label: "Cyanobakterier",type: "cont", cmap: "cyano" },
  { key: "bentos",label: "Bottenfauna",   type: "cont", cmap: "bio" },
  { key: "sill",  label: "Sill",          type: "cont", cmap: "bio" },
  { key: "torsk", label: "Torsk",         type: "cont", cmap: "bio" },
  { key: "abborre",label:"Abborre",       type: "cont", cmap: "bio" },
  { key: "gadda", label: "Gädda",         type: "cont", cmap: "bio" },
  { key: "lax",   label: "Lax",           type: "cont", cmap: "bio" },
  { key: "havsoring", label: "Havsöring", type: "cont", cmap: "bio" },
  { key: "smorbult", label: "Svartmunnad smörbult", type: "cont", cmap: "bio" },
  { key: "nejonoga", label: "Flodnejonöga", type: "cont", cmap: "bio" },
  { key: "spigg", label: "Spigg",         type: "cont", cmap: "bio" },
  { key: "fagel", label: "Sjöfågel",      type: "cont", cmap: "bio" },
  { key: "temp",  label: "Temperatur",    type: "cont", cmap: "temp" },
  { key: "salinity", label: "Salthalt",   type: "cont", cmap: "sal" },
];

const CMAPS = {
  oxy:   [[0,[210,60,60]],[0.35,[230,180,70]],[0.65,[80,200,180]],[1,[70,150,230]]],
  bio:   [[0,[12,40,55]],[0.5,[40,170,150]],[1,[130,245,185]]],
  cyano: [[0,[15,40,28]],[0.5,[130,165,45]],[1,[210,225,90]]],
  temp:  [[0,[70,130,225]],[0.5,[130,205,160]],[1,[235,95,70]]],
  sal:   [[0,[130,195,215]],[1,[25,65,150]]],
};

const COL = {
  N:"#9fb3c8", phyto:"#4ade80", cyano:"#cbd44a", zoo:"#33c2c2", bentos:"#b08968",
  sill:"#4ea8ff", skarpsill:"#67e8f9", spigg:"#ffb454", abborre:"#a3e635",
  gadda:"#4d7c0f", torsk:"#ff6b6b", lax:"#fb7185", havsoring:"#f472b6",
  smorbult:"#9a6b4f", nejonoga:"#94a3b8", fagel:"#e879f9", sal:"#c084fc",
  O2:"#7dd3fc", O2b:"#2563eb", det:"#8aa9c4",
};
// Färgpalett för uttag och trofinivåer
const UCOL = { fiske:"#ff6b6b", sal:"#c084fc", skarv:"#e879f9", atervinning:"#4ade80" };
const TROFI_COL = ["#9fb3c8","#4ade80","#33c2c2","#4ea8ff","#a3e635","#ff6b6b","#e879f9","#8aa9c4"];
// Levande biomassa som visas i kartans tårtdiagram (uteslut näring/syre/detritus)
const BIOMASS = ["phyto","cyano","zoo","bentos","sill","skarpsill","spigg","abborre","gadda","smorbult","torsk","lax","havsoring","nejonoga","fagel","sal"];

const PRESETS = {
  plankton: ["N","phyto","cyano","zoo"],
  fisk: ["sill","skarpsill","spigg","mort","flundra","smorbult","abborre","gadda","torsk","lax","havsoring","nejonoga"],
  botten: ["bentos","flundra","smorbult","O2b","det"],
  syre: ["O2","O2b"],
  allt: ["N","phyto","cyano","zoo","bentos","sill","skarpsill","spigg","mort","flundra","smorbult","abborre","gadda","torsk","lax","havsoring","nejonoga","fagel","sal","O2","O2b"],
};

const $ = (id) => document.getElementById(id);
const T = (k, fallback) => STR[k] || fallback || k;

// Donation: sätt DONATE_URL till din Swish-/PayPal-/Buy-Me-a-Coffee-länk.
// Är den tom faller knappen tillbaka på ett mejl till kontaktadressen.
const CONTACT_EMAIL = "hugo.wikstrom@gmail.com";
const DONATE_URL = "";   // ← klistra in din donationslänk här (t.ex. https://buymeacoffee.com/…)
function donateHref() {
  return DONATE_URL ||
    `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Stöd till Eystrasalt")}`;
}

// Reglage-beteende: klick på pricken → standardvärde, klick vänster/höger om
// pricken → ett steg ner/upp, dra pricken → flytta fritt (native).
function enhanceSlider(slider) {
  const THUMB_PX = 15;
  let downX = null, moved = false, onThumb = false;
  const thumbX = () => {
    const r = slider.getBoundingClientRect();
    const mn = +slider.min, mx = +slider.max;
    const frac = mx > mn ? (+slider.value - mn) / (mx - mn) : 0;
    return r.left + frac * r.width;
  };
  const setVal = (v) => {
    const mn = +slider.min, mx = +slider.max, step = +slider.step || 1;
    v = Math.min(mx, Math.max(mn, Math.round(v / step) * step));
    if (v === +slider.value) { slider.dispatchEvent(new Event("input", { bubbles: true })); return; }
    slider.value = v;
    slider.dispatchEvent(new Event("input", { bubbles: true }));
  };
  slider.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    downX = e.clientX; moved = false;
    const tx = thumbX();
    onThumb = Math.abs(e.clientX - tx) <= THUMB_PX;
    if (!onThumb) {                       // klick på baren → ett steg mot klicket
      e.preventDefault();
      const step = +slider.step || 1;
      setVal(+slider.value + (e.clientX < tx ? -step : step));
    }
  });
  slider.addEventListener("pointermove", (e) => {
    if (downX !== null && Math.abs(e.clientX - downX) > 3) moved = true;
  });
  const up = () => {
    if (onThumb && !moved) {              // ren klick på pricken → standardvärde
      const def = parseFloat(slider.defaultValue);
      if (!isNaN(def)) setVal(def);
    }
    downX = null; onThumb = false; moved = false;
  };
  slider.addEventListener("pointerup", up);
  slider.addEventListener("pointercancel", up);
}

// Säker HTML-escaping av användarinnehåll (F-01: hindrar lagrad XSS när text från
// idélåda, publikationer, sparade körningar och användarnamn renderas via innerHTML).
function escHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
// Escaping för värden som hamnar i ett HTML-attribut (t.ex. data-params='…').
const escAttr = escHtml;
const BASE_YEAR = 2025;    // simuleringens startår (år 0 = nuläge)
// Språkkod → talspråk (locale) för webbläsarens tala-till-text
const LOCALE = { sv:"sv-SE", en:"en-US", fi:"fi-FI", et:"et-EE", lv:"lv-LV",
                 lt:"lt-LT", ru:"ru-RU", pl:"pl-PL", de:"de-DE", da:"da-DK" };
let recognition = null, recognizing = false;

// Enkel markdown → HTML (fetstil **x**, kursiv *x*, rubriker ##, punktlistor)
function mdToHtml(t) {
  if (!t) return "";
  const esc = s => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  const inl = s => esc(s).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/\*(.+?)\*/g,"<i>$1</i>");
  const out = []; let inList = false;
  t.split(/\n/).forEach(line => {
    line = line.trim(); let m;
    if (!line) { if (inList) { out.push("</ul>"); inList = false; } return; }
    if ((m = line.match(/^#{1,4}\s*(.+)/))) { if (inList){out.push("</ul>");inList=false;} out.push("<h4>"+inl(m[1])+"</h4>"); return; }
    if ((m = line.match(/^[-*•]\s+(.+)/))) { if (!inList){out.push("<ul>");inList=true;} out.push("<li>"+inl(m[1])+"</li>"); return; }
    if (inList) { out.push("</ul>"); inList = false; }
    out.push("<p>"+inl(line)+"</p>");
  });
  if (inList) out.push("</ul>");
  return out.join("");
}

// ---- Färghjälp ----
function lerpColor(cmap, t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < cmap.length; i++) {
    if (t <= cmap[i][0]) {
      const [p0, c0] = cmap[i-1], [p1, c1] = cmap[i];
      const f = (t - p0) / (p1 - p0 || 1);
      const c = c0.map((v, k) => Math.round(v + (c1[k]-v)*f));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }
  }
  const c = cmap[cmap.length-1][1];
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

// ---- i18n ----
// Flagg-emoji per språkkod (liten, snygg språkväljare högst upp).
const FLAG = { sv:"🇸🇪", en:"🇬🇧", fi:"🇫🇮", et:"🇪🇪", lv:"🇱🇻", lt:"🇱🇹",
               ru:"🇷🇺", pl:"🇵🇱", de:"🇩🇪", da:"🇩🇰" };
const LANG_CACHE = {};   // klient-cache: byte till redan hämtat språk sker momentant
let currentLang = "sv";

async function loadLang(code) {
  // Momentant byte: använd cachad tabell direkt om vi redan hämtat språket.
  if (LANG_CACHE[code]) {
    STR = LANG_CACHE[code];
  } else {
    try {
      STR = await (await fetch("/api/i18n/" + code)).json();
      LANG_CACHE[code] = STR;
    } catch (e) { STR = LANG_CACHE.sv || {}; }
  }
  currentLang = code;
  applyI18n();
  localStorage.setItem("eystra_lang", code);
  document.documentElement.lang = code;
  const lsel = $("lang"); if (lsel) lsel.value = code;
  markActiveFlag(code);
  refreshDynamic();   // rita om dynamiskt innehåll (grafer, listor, matris) på nya språket
}

function markActiveFlag(code) {
  document.querySelectorAll("#flags .flag").forEach(b =>
    b.classList.toggle("active", b.dataset.lang === code));
}

function buildFlags(langs) {
  const box = $("flags"); if (!box) return;
  box.innerHTML = "";
  langs.forEach(l => {
    const b = document.createElement("button");
    b.className = "flag";
    b.dataset.lang = l.code;
    b.type = "button";
    b.title = l.native;
    b.setAttribute("aria-label", l.native);
    b.textContent = FLAG[l.code] || l.code.toUpperCase();
    b.addEventListener("click", () => loadLang(l.code));
    box.appendChild(b);
  });
}

// Rita om det språkberoende, dynamiska innehållet efter ett språkbyte (momentant).
function refreshDynamic() {
  try { if (typeof RES !== "undefined" && RES) drawAllCharts(); } catch (e) {}
  try { renderMatrix(); } catch (e) {}
  try { updateModeDesc(); } catch (e) {}
  try { renderUser(); } catch (e) {}
  try { if ($("view-saved") || document.getElementById("saved-list")) loadSavedList(); } catch (e) {}
  try { if ($("view-reports") && $("view-reports").classList.contains("active")) loadReports(); } catch (e) {}
  try { if ($("view-ideas") && $("view-ideas").classList.contains("active")) loadIdeas(); } catch (e) {}
}
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const k = el.dataset.i18n; if (STR[k]) el.textContent = STR[k];
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    const k = el.dataset.i18nPh; if (STR[k]) el.placeholder = STR[k];
  });
  renderGaps();
}

// Kunskapsluckor: statisk lista (gap_1..gap_8) med inledande fetstil (**...**).
function renderGaps() {
  const el = $("gaps-list"); if (!el) return;
  const bold = s => escHtml(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  let html = "";
  for (let i = 1; i <= 8; i++) {
    const k = "gap_" + i;
    if (STR[k]) html += `<li>${bold(STR[k])}</li>`;
  }
  el.innerHTML = html;
}

// De 20 vanligaste politiska frågorna om Östersjön. Innehållet är på svenska
// (Sverige-/Östersjöspecifik debatt); ramen (rubriker, etiketter) språkanpassas
// via i18n. pro/con speglar DEBATTENS argument — inte verktygets ståndpunkt.
// sim = konkreta reglage/flikar att köra för att pröva frågan i modellen.
const POLITIK = [
  { q: "Ska gråsälen skyddsjagas för att gynna fisket?",
    pro: "Sälen tar mycket torsk och lax, sprider sälmask (torskens parasit) och slår sönder redskap — lokal jakt kan lätta trycket på hårt pressade bestånd.",
    con: "Gråsälen är en naturlig toppredator som nyss återhämtat sig från nära utrotning; fiskets problem beror mer på övergödning, syrebrist och torskens kollaps än på säl.",
    sim: "Dra upp reglaget «Säljakt» stegvis (0 → 2 → 5) och kör 30 år. Se om torsk och lax faktiskt ökar, eller om skarpsill/spigg tar över utrymmet. Jämför utfallet i Monte Carlo och väg ökad fiskefångst mot förlorad toppredator i Ekonomi-fliken." },
  { q: "Ska skarven (mellanskarv) skyddsjagas?",
    pro: "Skarven äter stora mängder kustfisk — abborre, gädda, mört — och kan tömma lokala vikar där bestånden redan är svaga.",
    con: "Skarvens påverkan är oftast lokal; kustfiskens nedgång drivs mest av storspiggen, övergödning och förlorade lek- och uppväxtmiljöer.",
    sim: "Öka «Skarv-/fågeljakt» och kör. Följ abborre, gädda och mört i kartlagren. Testa samma jakt med och utan minskad övergödning — vilket ger egentligen mest kustrovfisk?" },
  { q: "Ska vi tråla bort storspiggen för att bryta «spiggkrisen»?",
    pro: "Spiggen har exploderat och äter yngel av abborre, gädda och torsk (wasp-waist). En riktad reduktion skulle kunna bryta det låsta «spigghavet».",
    con: "Spiggen är ett symptom, inte orsaken — utan starka rovfiskar återkommer den snabbt. Trålning ger bifångst och kan störa näringsväven ytterligare.",
    sim: "Höj «Fisketryck spigg» och kör. Se om abborre/gädda/torsk återhämtar sig. Jämför med att i stället stärka rovfisken (sänk torsk- och gäddfisket) — vilken väg bryter fällan bäst och mest varaktigt?" },
  { q: "Ska det storskaliga industri-/foderfisket på skarpsill och sill fortsätta tillåtas?",
    pro: "Foderfisket ger råvara till fiskmjöl och -olja (foder till odlad lax, päls- och husdjur) samt jobb, och skarpsillsbeståndet är för tillfället stort.",
    con: "Det trålar bort basfödan som torsk, sjöfågel, säl och strömming lever på — och tar strömmingen (sillen) som kustsamhällena är beroende av, vilket urholkar hela näringsväven underifrån.",
    sim: "Höj «Fisketryck skarpsill» och «Fisketryck sill» och kör. Följ torsk, lax, sjöfågel och säl — ser du hur ett hårt uttag längst ned i kedjan fortplantar sig uppåt? Väg i Ekonomi-fliken foderfiskets värde mot förlorat värde av rovfisk och ekosystemtjänster." },
  { q: "Ska torskfisket förbli helt stoppat?",
    pro: "Östersjötorsken är kollapsad; fortsatt stopp är enda chansen till återhämtning av toppredatorn.",
    con: "Torsken återhämtar sig ändå inte (dålig kondition, syrebrist, magra bestånd) — stoppet drabbar fisket utan tydlig effekt.",
    sim: "Sätt «Fisketryck torsk» = 0 och kör 40–50 år. Kör sedan samma stopp men kombinera med högre salthalt och mindre övergödning. Svarar torsken bara när även livsmiljön åtgärdas?" },
  { q: "Hur hårt ska jordbrukets och avloppens näringsläckage minskas?",
    pro: "Minskad näringstillförsel är grundorsaksåtgärden — mindre algblomning, bättre bottensyre och ett friskare hav på sikt.",
    con: "Dyrt för jordbruk och kommuner, och effekten är trög: intern fosforbelastning från döda bottnar gör att havet svarar först efter årtionden.",
    sim: "Sänk «Näringsbelastning» (1.0 → 0.5) och kör 50 år. Följ bottensyre och cyanobakterier. Använd Ekonomi-fliken för att väga åtgärdskostnaden mot värdet av återställda ekosystemtjänster." },
  { q: "Ska bottentrålning förbjudas?",
    pro: "Trålen skadar bottnar och bottenfauna, grumlar vattnet och ger stor bifångst av bl.a. torsk.",
    con: "Bottentrålning är central för delar av fiskerinäringen; skonsammare redskap är dyrare och mindre effektiva.",
    sim: "Sänk fisketrycket på de bottennära arterna (torsk, flundra) och kör. Följ bottenfauna och flundra över tid som mått på bottnarnas återhämtning." },
  { q: "Ska staten storskaligt syresätta de döda bottnarna (pumpning)?",
    pro: "Syresättning kan bryta den interna fosforcykeln lokalt och väcka liv i syrefria bottnar snabbare än näringsminskning.",
    con: "Mycket dyrt, oprövat i stor skala och åtgärdar symptomet, inte källan (näringen) — risk för nya störningar.",
    sim: "Modellens saltvatteninflöden (MBI) är naturens egen syresättning. Kör flera slumpfrön (brus) och se hur länge en syrepuls håller innan djupbassängen blir syrefri igen — ett mått på hur ofta konstgjord syresättning måste upprepas." },
  { q: "Ska musselodling subventioneras som näringsrening?",
    pro: "Musslor filtrerar växtplankton och binder näring som skördas bort ur havet — en «blå» reningsmetod som även ger foder.",
    con: "I det söta norr blir musslorna små och odlingen ineffektiv; kostnaden per kilo bortförd fosfor är omdiskuterad.",
    sim: "Följ bottenfauna (filtrerarna) i kartan vid olika näringsnivåer och se hur mycket deras filtrering trycker ned växtplankton — en indikation på filtreringens potential." },
  { q: "Hur ska fiskekvoterna fördelas mellan länder och mellan yrkes- och fritidsfiske?",
    pro: "Tydliga, rättvisa kvoter förhindrar överfiske och ger förutsägbarhet för näringen.",
    con: "Fördelningen är en het konflikt — små kustsamhällen, storskaligt trålfiske och sportfisket drar åt olika håll.",
    sim: "Kör olika fisketrycks-nivåer per art och jämför i Ekonomi-fliken, som visar värdet per land. Se hur totalfångst vs långsiktigt bestånd förändras med hårdare respektive mildare kvoter." },
  { q: "Ska vi satsa på kustrestaurering — «gäddfabriker» och våtmarker?",
    pro: "Återställda våtmarker och grunda vikar ger lek- och uppväxtmiljöer som bygger upp abborre och gädda underifrån.",
    con: "Storskalig nytta är osäker och lokal; markåtkomst och kostnad är hinder.",
    sim: "Kombinera en liten utsötning (gynnar kustrovfisk) med lägre spiggtryck och kör. Följ abborre och gädda i norra/kustnära zoner." },
  { q: "Ska lax- och havsöringsvatten prioriteras (fria vandringsvägar, årestaurering)?",
    pro: "Rivna vandringshinder och friska åar ger fler vildlaxar och havsöringar — höga natur- och sportfiskevärden.",
    con: "Krockar med vattenkraft och markägare; kostsamt och långsamt.",
    sim: "Sänk «Fisketryck lax» respektive «Fisketryck havsöring» och jämför. Notera skillnaden i modellen: laxen är havsvandrande (åtgärder måste tänkas storskaligt) medan havsöringen är kustbunden (lokala åtgärder nära hemån biter direkt)." },
  { q: "Hur ska vi hantera klimatförändringens uppvärmning och utsötning?",
    pro: "Att planera för ett varmare, sötare hav är nödvändigt — annars slår förändringen ut torsken och gynnar cyanobakterier oväntat.",
    con: "Östersjöländerna kan inte styra klimatet ensamma; risk att lokala åtgärder överskuggas av global uppvärmning.",
    sim: "Höj «Klimatuppvärmning» och sänk «Salthaltsändring» och kör. Se torsken minska, kustrovfisk och cyanobakterier öka, och bottensyret försämras — testa vilka lokala åtgärder som mildrar mest." },
  { q: "Ska de marina skyddsområdena utökas och fredas helt från fiske?",
    pro: "Helt fredade områden låter hela näringsväven återhämta sig och fungerar som barnkammare som spiller över till omgivningen.",
    con: "Begränsar fisket och kräver övervakning; effekten uteblir om övergödningen kvarstår.",
    sim: "Sätt allt fisketryck lågt (ett fredningsscenario) och kör. Jämför hela näringsvävens och hälsoindexets återhämtning mot baslinjen i Monte Carlo." },
  { q: "Hur mycket ska vi investera i avloppsrening?",
    pro: "Modern rening (kväve/fosfor) är en av de mest kostnadseffektiva åtgärderna mot övergödning.",
    con: "Stora investeringar för kommuner; en del läckage kommer från jordbruk och kan inte renas i verk.",
    sim: "Sänk «Näringsbelastning» måttligt och kör; jämför bottensyre och algnivåer. Ekonomi-fliken visar om nyttan (tjänster) motiverar investeringen." },
  { q: "Ska vi införa handel med näringsutsläppsrätter mellan länder?",
    pro: "Marknadsstyrning kan ge störst näringsminskning per krona genom att åtgärda där det är billigast.",
    con: "Svårt att mäta och kontrollera; risk att utsläppen bara flyttar mellan bassänger.",
    sim: "Näringsbelastningen är zonvis i modellen. Kör olika minskningar och jämför hur syre och alger svarar i just den övergödda zonen — en indikation på var åtgärder ger mest." },
  { q: "Ska Östersjöländerna binda sig vid gemensamma, bindande mål (BSAP)?",
    pro: "Havet delas av nio länder — bara samordnade, bindande mål räcker mot ett gemensamt problem.",
    con: "Bindande mål inskränker nationellt självbestämmande och riskerar att bli tröga att förhandla.",
    sim: "Kör det kombinerade åtgärdspaketet (minskad övergödning + minskat fiske samtidigt) och jämför med enstaka åtgärder — visar värdet av att göra allt på en gång." },
  { q: "Ska vi prioritera kortsiktiga fiskeintäkter eller långsiktiga ekosystemtjänster?",
    pro: "Fisket ger jobb och mat här och nu; för hårda restriktioner slår mot kustsamhällen direkt.",
    con: "Överuttag idag urholkar bestånd och tjänster som är värda långt mer på sikt.",
    sim: "Kör samma strategi över kort (10 år) och lång (50 år) horisont i Ekonomi-fliken och jämför värdet — gör avvägningen synlig i siffror." },
  { q: "Ska vattenbruk och fiskodling byggas ut i Östersjön?",
    pro: "Odlad fisk minskar trycket på vilda bestånd och ger lokal matproduktion.",
    con: "Öppna kassar läcker näring och kan förvärra övergödningen lokalt.",
    sim: "Höj «Näringsbelastning» något (motsvarar lokalt näringstillskott) och kör; se effekten på alger och syre i den zonen — väg mot minskat uttag av vildfisk." },
  { q: "Ska torsken aktivt återintroduceras, eller ska vi lita på naturlig återhämtning?",
    pro: "Aktiv utsättning kan snabba på återkomsten om den naturliga rekryteringen har fastnat.",
    con: "Utan rätt salthalt och syre svälter/dör utsatt torsk ändå — pengar i sjön.",
    sim: "Kör torskstopp med och utan förbättrad livsmiljö (högre salthalt, mindre övergödning). Om torsken bara svarar när miljön förbättras är utsättning ensam lönlös." },
  { q: "Ska säl och skarv skyddsjagas samtidigt, eller inte alls?",
    pro: "Båda är toppredatorer på fisk; samlad skyddsjakt skulle kunna ge tydligare effekt för fisket än att jaga bara den ena.",
    con: "Att slå mot två toppredatorer samtidigt kan destabilisera näringsväven och gynna spigg och skräpfisk mer än nyttofisk.",
    sim: "Höj «Säljakt» och «Skarv-/fågeljakt» tillsammans och kör; jämför med att bara höja den ena. Följ nyttofisk, spigg och hälsoindex — ger dubbel jakt dubbel nytta eller oväntade bakslag?" },
  { q: "Hur hårt ska miljögifterna fasas ut (dioxin, PCB, läkemedel, mikroplast)?",
    pro: "Östersjöns strömming, lax och öring har så höga dioxin- och PCB-halter att det finns kostråd — utfasning skyddar folkhälsan och gör fisken säljbar igen.",
    con: "Gamla synder (dioxin/PCB) sitter kvar i sedimenten och avtar långsamt oavsett åtgärder; nya krav som läkemedelsrening är dyra för kommunerna.",
    sim: "Modellen simulerar inte gifter direkt, men den visar vägen de tar: miljögifter anrikas uppåt i näringskedjan. Följ toppredatorerna (lax, havsöring, säl) — ju större deras andel av uttaget, desto mer giftanrikning bär fångsten. Använd näringsvävens struktur (Ekologimatris) för att resonera om exponeringen." },
  { q: "Hur ska havets hälsa vägas mot ekonomisk utveckling (sjöfart, hamnar, kustexploatering)?",
    pro: "Sjöfart, hamnar, turism och kustbebyggelse skapar jobb och tillväxt som regionen behöver.",
    con: "Muddring, utfyllnad, buller och utsläpp tär på grunda livsmiljöer som inte kan återställas — kortsiktig tillväxt mot bestående naturförlust.",
    sim: "Verktyget sätter pris på naturen. Kör Ekonomi-fliken och jämför värdet av ekosystemtjänster (ett friskt hav) mot fiskeintäkterna under olika strategier — en siffra att ställa mot exploateringens intäkter i en samhällsekonomisk avvägning." },
];

// Renderar politik-frågorna som kort. Etiketterna (För/Emot/Simuleringar)
// språkanpassas via i18n; frågeinnehållet är på svenska.
function renderPolitik() {
  const el = $("politik-list"); if (!el) return;
  const lFor = T("politik_for", "Argument för");
  const lCon = T("politik_emot", "Argument emot");
  const lSim = T("politik_sim", "Simuleringar att köra");
  el.innerHTML = POLITIK.map((p, i) => `
    <div class="pol-card">
      <div class="pol-q"><span class="pol-num">${i + 1}</span>${escHtml(p.q)}</div>
      <div class="pol-row pol-for"><span class="pol-lbl">${escHtml(lFor)}</span>${escHtml(p.pro)}</div>
      <div class="pol-row pol-con"><span class="pol-lbl">${escHtml(lCon)}</span>${escHtml(p.con)}</div>
      <div class="pol-row pol-sim"><span class="pol-lbl">${escHtml(lSim)}</span>${escHtml(p.sim)}</div>
    </div>`).join("");
}

// ---- Karta ----
function layerValue(layer, zone, i) {
  if (layer.key === "temp") return RES.env.temp[zone][i];
  if (layer.key === "salinity") return RES.env.salinity[zone][i];
  if (layer.key === "status") return RES.series[zone].O2b[i];
  return RES.series[zone][layer.key][i];
}
function layerRange(layer) {
  let lo = Infinity, hi = -Infinity;
  for (const z of RES.zones) {
    const arr = layer.key === "temp" ? RES.env.temp[z]
              : layer.key === "salinity" ? RES.env.salinity[z]
              : RES.series[z][layer.key === "status" ? "O2b" : layer.key];
    for (const v of arr) { if (v < lo) lo = v; if (v > hi) hi = v; }
  }
  return [lo, hi];
}
function statusColor(o2b) {
  if (o2b >= 50) return "#4ade80";
  if (o2b >= 15) return "#ffb454";
  return "#ff5252";
}

// Radien för en zon (djupa bassänger något större)
function zoneR(z) { return z.has_deep_basin ? 11 : 8.5; }
// Punkt på cirkeln vid vinkel a (radianer, 0 = uppåt)
function polar(cx, cy, r, a) { return [cx + r*Math.sin(a), cy - r*Math.cos(a)]; }

function buildMap() {
  const svg = $("map");
  // Klick delegeras (innehållet byggs om vid varje tidssteg)
  svg.addEventListener("click", e => {
    const g = e.target.closest("[data-zone]");
    if (g) selectZone(g.dataset.zone);
  });
  updateMap();
}

// Kort talformat: 1234 → "1.2k"
function shortNum(v) {
  if (v >= 1000) return (v/1000).toFixed(v >= 10000 ? 0 : 1) + "k";
  if (v >= 100) return v.toFixed(0);
  return v.toFixed(v < 10 ? 1 : 0);
}
// Kort enhet per kartlager (till värdet som skrivs i varje region)
function layerUnit(layer) {
  if (layer.key === "temp") return "°C";
  if (layer.key === "salinity") return "PSU";
  if (layer.key === "O2" || layer.key === "O2b") return "%";
  return "g/m²";   // biomassa (g/m² ≈ ton/km²)
}

// Tårtdiagram för en zon: tårtbitar per art + totalmassa i mitten
function pieSvg(z) {
  const s = RES.series[z], zd = DEF.zones.find(x => x.key === z);
  const cx = zd.x, cy = zd.y, r = zoneR(z);
  const vals = BIOMASS.map(c => Math.max(0, s[c][ti]));
  const total = vals.reduce((a, b) => a + b, 0);
  const sel = z === selectedZone;
  let out = "";
  if (total <= 0) {
    out += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#0d2135"/>`;
  } else {
    let a0 = 0;
    BIOMASS.forEach((c, k) => {
      const frac = vals[k] / total;
      if (frac <= 0) return;
      const a1 = a0 + frac * 2 * Math.PI;
      if (frac >= 0.999) {           // en enda art fyller cirkeln
        out += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${COL[c]}"/>`;
      } else {
        const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
        const large = (a1 - a0) > Math.PI ? 1 : 0;
        out += `<path d="M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} `
             + `A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z" `
             + `fill="${COL[c]}"/>`;
      }
      a0 = a1;
    });
  }
  // Hål i mitten (munk) + totalsiffra
  out += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" `
       + `stroke="${sel ? '#fff' : '#0a1929'}" stroke-width="${sel ? 1.1 : 0.5}"/>`;
  out += `<circle cx="${cx}" cy="${cy}" r="${r*0.5}" fill="#0d2135" opacity="0.9"/>`;
  out += `<text x="${cx}" y="${cy}" class="pie-total">${shortNum(total)}</text>`;
  out += `<text x="${cx}" y="${cy+2.3}" class="pie-unit">g/m²</text>`;
  out += `<text x="${cx}" y="${cy + r + 3}" class="zone-label">${zd.name}</text>`;
  return `<g data-zone="${z}" style="cursor:pointer">${out}</g>`;
}

function updateMap() {
  if (!RES) return;
  const layer = LAYERS.find(l => l.key === $("layer").value) || LAYERS[0];
  const svg = $("map");
  const pos = {}; DEF.zones.forEach(z => pos[z.key] = z);
  let parts = "";
  // Grannlänkar
  ADJ.forEach(([a,b]) => {
    parts += `<line x1="${pos[a].x}" y1="${pos[a].y}" x2="${pos[b].x}" y2="${pos[b].y}" `
           + `stroke="#1e4260" stroke-width="0.8"/>`;
  });
  if (layer.type === "pie") {
    DEF.zones.forEach(z => parts += pieSvg(z.key));
    svg.innerHTML = parts;
    drawPieLegend();
    return;
  }
  // Choropleth (enkel färg per zon)
  const [lo, hi] = layer.type === "cont" ? layerRange(layer) : [0,0];
  DEF.zones.forEach(z => {
    const r = zoneR(z);
    const v = layerValue(layer, z.key, ti);
    const color = layer.type === "status" ? statusColor(v)
                : lerpColor(CMAPS[layer.cmap], (v - lo) / (hi - lo || 1));
    const sel = z.key === selectedZone;
    const unit = layerUnit(layer);
    parts += `<g data-zone="${z.key}" style="cursor:pointer">`
           + `<circle cx="${z.x}" cy="${z.y}" r="${r}" fill="${color}" `
           + `stroke="${sel ? '#fff' : '#0a1929'}" stroke-width="${sel ? 1.4 : 0.6}"/>`
           + `<text x="${z.x}" y="${z.y+0.2}" class="pie-total">${shortNum(v)}</text>`
           + `<text x="${z.x}" y="${z.y+2.5}" class="pie-unit">${unit}</text>`
           + `<text x="${z.x}" y="${z.y + r + 3}" class="zone-label">${z.name}</text></g>`;
  });
  svg.innerHTML = parts;
  drawLegend(layer, lo, hi);
}

// Färgnyckel för tårtdiagrammens arter
function drawPieLegend() {
  $("legend").innerHTML =
    `<span style="width:100%;color:var(--muted)">${T("pie_legend","Tårtbitar = art, siffran i mitten = total biomassa")}</span>` +
    BIOMASS.map(c => `<span><span class="swatch" style="background:${COL[c]}"></span>${RES.display[c]}</span>`).join("");
}
function drawLegend(layer, lo, hi) {
  const el = $("legend");
  if (layer.type === "status") {
    el.innerHTML = `<span><span class="swatch" style="background:#4ade80"></span>Syrerik botten</span>
      <span><span class="swatch" style="background:#ffb454"></span>Syrefattig (hypoxi)</span>
      <span><span class="swatch" style="background:#ff5252"></span>Syrefri (död botten)</span>`;
    return;
  }
  const stops = [];
  for (let i = 0; i <= 6; i++) stops.push(lerpColor(CMAPS[layer.cmap], i/6));
  const unit = (layer.key === "temp") ? " °C" : (layer.key === "salinity") ? " PSU"
             : (layer.key === "O2" || layer.key === "O2b") ? " % mättn." : "";
  el.innerHTML = `<span>${lo.toFixed(1)}${unit}</span>
    <span class="bar" style="background:linear-gradient(90deg,${stops.join(",")})"></span>
    <span>${hi.toFixed(1)}${unit}</span>`;
}


// ---- Valbara linjediagram (auto-skala + enhet) ----
function drawLines(id, comps, opts) {
  opts = opts || {};
  const el = $(id);
  const W = 360, H = 150, ml = 34, mr = 8, mt = 8, mb = 18;
  const t = RES.t, n = t.length;
  const s = RES.series[selectedZone];
  const norm = !!opts.normalize;

  const perMax = {};
  comps.forEach(c => { let m = 0; s[c].forEach(v => { if (v > m) m = v; }); perMax[c] = m || 1; });
  let ymax = norm ? 100 : Math.max(...comps.map(c => perMax[c]), 1e-9) * 1.1;
  const val = (c, v) => norm ? (v / perMax[c]) * 100 : v;

  const xmax = t[n-1];
  const X = (x) => ml + (x / xmax) * (W - ml - mr);
  const Y = (y) => mt + (1 - y / ymax) * (H - mt - mb);

  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let k = 0; k <= 2; k++) {
    const yy = (ymax * k / 2);
    svg += `<line class="gridline" x1="${ml}" y1="${Y(yy)}" x2="${W-mr}" y2="${Y(yy)}"/>`;
    svg += `<text class="axis-label" x="2" y="${Y(yy)+3}">${yy.toFixed(yy<10?1:0)}</text>`;
  }
  for (let k = 0; k <= 4; k++) {
    const xx = xmax * k / 4;
    svg += `<text class="axis-label" x="${X(xx)-8}" y="${H-4}">${(BASE_YEAR+xx).toFixed(0)}</text>`;
  }
  comps.forEach(c => {
    let pts = "";
    for (let i = 0; i < n; i++) pts += `${X(t[i]).toFixed(1)},${Y(val(c, s[c][i])).toFixed(1)} `;
    svg += `<polyline points="${pts}" fill="none" stroke="${COL[c]}" stroke-width="1.4"/>`;
  });
  svg += `<line class="cursor" x1="${X(t[ti])}" y1="${mt}" x2="${X(t[ti])}" y2="${H-mb}" stroke="#fff" stroke-width="0.6" opacity="0.6"/>`;
  svg += `</svg>`;
  el.innerHTML = svg;

  const units = new Set(comps.map(c => DEF.units[c]));
  $("unit-main").textContent = norm ? "Y-axel: % av varje series egna maxvärde"
    : "Y-axel: " + (units.size === 1 ? [...units][0] : "blandade enheter — slå på Normalisera för att jämföra former");
}

function drawHealthChart() {
  if (!RES || !RES.health) return;
  const el = $("chart-health");
  const W = 360, H = 90, ml = 26, mr = 8, mt = 6, mb = 16;
  // Hälsa för den markerade zonen (faller tillbaka på hela havet)
  const hz = (RES.health_zones && RES.health_zones[selectedZone]) || RES.health;
  const ys = hz.years, vs = hz.index, n = ys.length;
  const xmax = ys[n-1] || 1;
  const X = (x) => ml + (x / xmax) * (W - ml - mr);
  const Y = (y) => mt + (1 - y / 100) * (H - mt - mb);
  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  [0,50,100].forEach(g => {
    svg += `<line class="gridline" x1="${ml}" y1="${Y(g)}" x2="${W-mr}" y2="${Y(g)}"/>`;
    svg += `<text class="axis-label" x="2" y="${Y(g)+3}">${g}</text>`;
  });
  let pts = "";
  for (let i = 0; i < n; i++) pts += `${X(ys[i]).toFixed(1)},${Y(vs[i]).toFixed(1)} `;
  svg += `<polyline points="${pts}" fill="none" stroke="#4ade80" stroke-width="1.8"/>`;
  const cur = vs[n-1];
  const zn = RES.zone_names ? RES.zone_names[selectedZone] : "";
  svg += `<text class="serie-label" x="${ml+2}" y="10" fill="#4ade80">${zn} — ${T("health_title","Hälsoindex")}: ${cur.toFixed(0)}/100</text>`;
  svg += `</svg>`;
  el.innerHTML = svg;
}

function buildChips() {
  const el = $("series-chips");
  el.innerHTML = "";
  RES.compartments.forEach(c => {
    const chip = document.createElement("span");
    chip.className = "chip" + (selectedSeries.has(c) ? " on" : "");
    chip.innerHTML = `<span class="dot" style="background:${COL[c]}"></span>${RES.display[c]}`;
    chip.addEventListener("click", () => {
      if (selectedSeries.has(c)) selectedSeries.delete(c); else selectedSeries.add(c);
      buildChips(); drawMainChart();
    });
    el.appendChild(chip);
  });
}
function drawMainChart() {
  const comps = RES.compartments.filter(c => selectedSeries.has(c));
  if (!comps.length) { $("chart-main").innerHTML = ""; $("unit-main").textContent = ""; return; }
  drawLines("chart-main", comps, { normalize: $("normalize").checked });
}
// Pil + procentuell förändring mellan två värden (för trendkolumnerna)
function trendArrow(from, to) {
  if (from <= 1e-9 && to <= 1e-9) return `<span class="tr-flat">–</span>`;
  const ch = from > 1e-9 ? (to - from) / from : 1;   // relativ förändring
  const pct = (ch * 100);
  const txt = (pct >= 0 ? "+" : "") + pct.toFixed(0) + " %";
  if (ch > 0.05) return `<span class="tr-up">▲ ${txt}</span>`;
  if (ch < -0.05) return `<span class="tr-down">▼ ${txt}</span>`;
  return `<span class="tr-flat">→ ${txt}</span>`;
}

// Medelvärde av en serie i ett 3-årsfönster kring ett givet år. Brett fönster
// eftersom vissa arter (särskilt djurplankton) svänger kraftigt med flerårig
// takt — ett smalt fönster ger annars orimliga jämförelsetal (aliasing).
function annMean(arr, t, year) {
  let sum = 0, n = 0;
  for (let i = 0; i < t.length; i++) {
    if (t[i] >= year - 1.5 && t[i] <= year + 1.5) { sum += arr[i]; n++; }
  }
  if (n) return sum / n;
  let bi = 0, bd = Infinity;                     // fallback: närmaste punkt
  for (let i = 0; i < t.length; i++) { const d = Math.abs(t[i] - year); if (d < bd) { bd = d; bi = i; } }
  return arr[bi];
}

// Sammanställning under grafen: biomassa, andel, kort/lång sikt, % av idag.
// Alla värden är ÅRSMEDEL (annars stör säsongssvängningen jämförelserna).
function drawBiomassTable() {
  const el = $("biomass-table");
  if (!el || !RES) return;
  const s = RES.series[selectedZone], t = RES.t;
  const yEnd = t[t.length - 1];
  const yNow = t[ti];
  const yShort = Math.min(5, yEnd);              // "kort sikt" ≈ 5 år
  const M = (c, y) => Math.max(0, annMean(s[c], t, y));
  // "Idag" = medel över första 3 åren (dämpar spinup/säsong/flerårstakt)
  const M0 = (c) => {
    let sum = 0, n = 0;
    for (let i = 0; i < t.length; i++) { if (t[i] <= 3.0) { sum += s[c][i]; n++; } }
    return n ? Math.max(0, sum / n) : M(c, 0);
  };

  let totNow = 0;
  BIOMASS.forEach(c => { totNow += M(c, yNow); });

  const row = (namn, col, start, now, sh, end) => {
    const andel = totNow > 0 ? (now / totNow * 100) : 0;
    // % av idag: skydda mot division med nära-noll (frånvarande art idag)
    const mot = start > 0.02 ? (now / start * 100) : null;
    const motCls = mot == null ? "" : (mot >= 100 ? "pos" : "neg");
    const motTxt = mot == null ? (now > 0.02 ? "ny" : "–") : mot.toFixed(0) + " %";
    const dot = col ? `<span class="dot" style="background:${col}"></span>` : "";
    return `<tr>
      <td>${dot}${namn}</td>
      <td>${now.toFixed(2)}</td>
      <td>${andel.toFixed(1)} %</td>
      <td>${trendArrow(start, sh)}</td>
      <td>${trendArrow(start, end)}</td>
      <td class="${motCls}">${motTxt}</td></tr>`;
  };

  let rows = BIOMASS.map(c =>
    row(RES.display[c], COL[c], M0(c), M(c, yNow), M(c, yShort), M(c, yEnd))).join("");
  // Totalrad
  let tStart = 0, tShort = 0, tEnd = 0;
  BIOMASS.forEach(c => { tStart += M0(c); tShort += M(c, yShort); tEnd += M(c, yEnd); });
  rows += `<tr class="tot-row">` + row(T("total_col","Totalt"), null, tStart, totNow, tShort, tEnd).slice(4);

  el.innerHTML = `<table class="biomass-tbl">
    <thead><tr>
      <th>${T("arter","Art")}</th>
      <th>${T("biomassa_col","Biomassa")}</th>
      <th>${T("share_col","Andel")}</th>
      <th>${T("short_term","Kort sikt")}</th>
      <th>${T("long_term","Lång sikt")}</th>
      <th>${T("vs_today","% av idag")}</th>
    </tr></thead><tbody>${rows}</tbody></table>
    <div class="hint">${T("biomass_hint","3-årsmedelvärden (dämpar säsongs- och flerårssvängningar). Kort sikt ≈ 5 år, lång sikt = hela förloppet, jämfört med idag (100 % = som idag).")}</div>`;
}

function drawAllCharts() { drawMainChart(); drawHealthChart(); drawBiomassTable(); drawCatchWeight(); drawPyramid(); drawUttak(); drawTrofi(); }

// Klick i grafen → sätt tidslinjen till klickat år (kartan/regionerna följer med)
function chartSeek(e) {
  if (!RES) return;
  const svg = $("chart-main").querySelector("svg");
  if (!svg || !svg.getScreenCTM) return;
  const pt = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());  // → viewBox-koord (0..360)
  const W = 360, ml = 34, mr = 8;
  const xmax = RES.t[RES.t.length - 1];
  let xdata = (p.x - ml) / (W - ml - mr) * xmax;
  xdata = Math.max(0, Math.min(xmax, xdata));
  // närmaste tidsindex
  let best = 0, bd = Infinity;
  for (let i = 0; i < RES.t.length; i++) {
    const d = Math.abs(RES.t[i] - xdata);
    if (d < bd) { bd = d; best = i; }
  }
  if (playing) play();   // pausa ev. uppspelning
  setTime(best);
}

function moveCursors() {
  const svg = $("chart-main").querySelector("svg");
  if (!svg) return;
  const line = svg.querySelector(".cursor");
  if (!line) return;
  const W = 360, ml = 34, mr = 8;
  const xmax = RES.t[RES.t.length-1];
  const px = ml + (RES.t[ti] / xmax) * (W - ml - mr);
  line.setAttribute("x1", px); line.setAttribute("x2", px);
}

// ---- Näringspyramid (kretslopp) ----
function drawPyramid() {
  if (!RES || !RES.trofi) return;
  const el = $("pyramid"); if (!el) return;
  const ord = RES.trofi.ordning;                 // botten→topp-ordning i listan
  const niv = RES.trofi.nivaer;
  const last = RES.trofi.years.length - 1;
  // Värden per nivå (sista året)
  const vals = ord.map(n => niv[n][last]);
  const maxv = Math.max(...vals, 1e-9);
  const W = 720, rowH = 40, gap = 6;
  const rows = ord.length;
  const H = rows * (rowH + gap) + 10;
  // Rita uppifrån (toppredatorer överst) → vänd listan
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="pyr">`;
  for (let r = 0; r < rows; r++) {
    const idx = rows - 1 - r;                     // toppen först
    const name = ord[idx], v = vals[idx];
    const frac = Math.sqrt(v / maxv);             // sqrt → tydligare små nivåer
    const bw = Math.max(60, frac * (W - 40));
    const x = (W - bw) / 2, y = 6 + r * (rowH + gap);
    const col = TROFI_COL[idx % TROFI_COL.length];
    svg += `<rect x="${x.toFixed(1)}" y="${y}" width="${bw.toFixed(1)}" height="${rowH}" rx="6"
              fill="${col}" opacity="0.85"/>`;
    svg += `<text x="${W/2}" y="${y+rowH/2-2}" class="pyr-name">${name}</text>`;
    svg += `<text x="${W/2}" y="${y+rowH/2+11}" class="pyr-val">${v.toFixed(2)}</text>`;
  }
  svg += `</svg>`;
  // Kretslopp-not: kadaver → nedbrytning → näring
  el.innerHTML = svg +
    `<p class="cycle-note">↻ Kretslopp: allt som dör (inkl. säl och fågel) → detritus/kadaver → nedbrytning → näringssalter igen.</p>`;
}

// ---- Multi-linjediagram (generellt: serier över år) ----
function multiLine(id, years, series, opts) {
  opts = opts || {};
  const el = $(id); if (!el) return;
  const W = 720, H = 200, ml = 40, mr = 10, mt = 10, mb = 22;
  const n = years.length, xmax = years[n-1] || 1;
  let ymax = 0;
  series.forEach(s => s.data.forEach(v => { if (v > ymax) ymax = v; }));
  ymax = (ymax || 1) * 1.1;
  const X = (x) => ml + (x / xmax) * (W - ml - mr);
  const Y = (y) => mt + (1 - y / ymax) * (H - mt - mb);
  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let k = 0; k <= 2; k++) {
    const yy = ymax * k / 2;
    svg += `<line class="gridline" x1="${ml}" y1="${Y(yy)}" x2="${W-mr}" y2="${Y(yy)}"/>`;
    svg += `<text class="axis-label" x="2" y="${Y(yy)+3}">${yy.toFixed(yy<10?1:0)}</text>`;
  }
  for (let k = 0; k <= 5; k++) {
    const xx = xmax * k / 5;
    svg += `<text class="axis-label" x="${X(xx)-8}" y="${H-6}">${(BASE_YEAR+xx).toFixed(0)}</text>`;
  }
  series.forEach(s => {
    let pts = "";
    for (let i = 0; i < n; i++) pts += `${X(years[i]).toFixed(1)},${Y(s.data[i]).toFixed(1)} `;
    svg += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="1.8"/>`;
  });
  svg += `</svg>`;
  el.innerHTML = svg;
}
function legendHtml(items) {
  return items.map(i => `<span><span class="swatch" style="background:${i.color}"></span>${i.label}</span>`).join("");
}

// Parallell graf: total biomassa (vikt) vs fångst över tid, med dubbla y-axlar
function drawCatchWeight() {
  const el = $("chart-catch");
  if (!el || !RES || !RES.uttak) return;
  const u = RES.uttak, t = RES.t, years = u.years, n = years.length;
  // Total biomassa (vikt) hela havet — årsmedel vid varje uttag-år
  const vikt = years.map(yr => {
    let sum = 0, cnt = 0;
    for (let i = 0; i < t.length; i++) {
      if (t[i] >= yr - 0.5 && t[i] <= yr + 0.5) {
        let s = 0; BIOMASS.forEach(c => s += Math.max(0, RES.totals[c][i]));
        sum += s; cnt++;
      }
    }
    return cnt ? sum / cnt : 0;
  });
  const fangst = u.fiske;
  const W = 720, H = 200, ml = 46, mr = 48, mt = 10, mb = 22;
  const xmax = years[n - 1] || 1;
  const maxV = Math.max(...vikt, 1e-9) * 1.1, maxF = Math.max(...fangst, 1e-9) * 1.1;
  const X = x => ml + (x / xmax) * (W - ml - mr);
  const YV = y => mt + (1 - y / maxV) * (H - mt - mb);
  const YF = y => mt + (1 - y / maxF) * (H - mt - mb);
  const cV = "#4ea8ff", cF = UCOL.fiske;         // vikt = blå, fångst = röd
  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let k = 0; k <= 2; k++) {
    const yy = maxV * k / 2, ff = maxF * k / 2;
    svg += `<line class="gridline" x1="${ml}" y1="${YV(yy)}" x2="${W - mr}" y2="${YV(yy)}"/>`;
    svg += `<text class="axis-label" x="2" y="${YV(yy) + 3}" fill="${cV}">${yy.toFixed(0)}</text>`;
    svg += `<text class="axis-label" x="${W - mr + 4}" y="${YF(ff) + 3}" fill="${cF}">${ff.toFixed(ff < 10 ? 1 : 0)}</text>`;
  }
  for (let k = 0; k <= 5; k++) {
    const xx = xmax * k / 5;
    svg += `<text class="axis-label" x="${X(xx) - 8}" y="${H - 6}">${(BASE_YEAR + xx).toFixed(0)}</text>`;
  }
  const poly = (data, Yf, col) => {
    let pts = ""; for (let i = 0; i < n; i++) pts += `${X(years[i]).toFixed(1)},${Yf(data[i]).toFixed(1)} `;
    return `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.8"/>`;
  };
  el.innerHTML = svg + poly(vikt, YV, cV) + poly(fangst, YF, cF) + `</svg>`;
  $("catch-legend").innerHTML =
    `<span><span class="swatch" style="background:${cV}"></span>${T("weight_series", "Total biomassa (vikt) — vänster axel")}</span>`
    + `<span><span class="swatch" style="background:${cF}"></span>${T("catch_series", "Fångst/fiske per år — höger axel")}</span>`
    + `<span class="band">${T("unit_rel_yr", "enhet: g/m² (vikt) resp. g/m²/år (fångst)")}</span>`;
}

function drawUttak() {
  if (!RES || !RES.uttak) return;
  const u = RES.uttak;
  const series = [
    { data: u.fiske, color: UCOL.fiske, label: "Fiske (människa)" },
    { data: u.sal, color: UCOL.sal, label: "Säl" },
    { data: u.skarv, color: UCOL.skarv, label: "Skarv/sjöfågel" },
  ];
  if (u.atervinning) series.push({ data: u.atervinning, color: UCOL.atervinning, label: "Återvinning (nedbrytning)" });
  multiLine("chart-uttak", u.years, series);
  $("uttak-legend").innerHTML = legendHtml(series) + `<span class="band">enhet: g/m²/år</span>`;
}
function drawTrofi() {
  if (!RES || !RES.trofi) return;
  const tr = RES.trofi;
  const series = tr.ordning.map((n, i) => ({ data: tr.nivaer[n], color: TROFI_COL[i % TROFI_COL.length], label: n }));
  multiLine("chart-trofi", tr.years, series);
  $("trofi-legend").innerHTML = legendHtml(series);
}

// ---- Zonval ----
function selectZone(z) {
  selectedZone = z;
  $("zone-name").textContent = RES ? RES.zone_names[z] : z;
  if (RES) { drawMainChart(); drawHealthChart(); drawBiomassTable(); updateMap(); }
}

// ---- Tidslinje ----
function setTime(i) {
  ti = Math.max(0, Math.min(RES.t.length-1, i|0));
  $("time").value = ti;
  $("time-label").textContent = "år " + (BASE_YEAR + RES.t[ti]).toFixed(0);
  updateMap(); moveCursors(); drawBiomassTable();
}
function play() {
  playing = !playing;
  $("play").textContent = playing ? "⏸" : "▶";
  if (playing) loop(); else cancelAnimationFrame(rafId);
}
let lastStep = 0;
function loop(tsNow) {
  if (!playing) return;
  if (!lastStep) lastStep = tsNow || 0;
  if ((tsNow || 0) - lastStep > 40) {
    lastStep = tsNow;
    let next = ti + 1;
    if (next >= RES.t.length) next = 0;
    setTime(next);
  }
  rafId = requestAnimationFrame(loop);
}

// ---- Reglage ----
function readParams() {
  return {
    years: +$("years").value,
    temp_delta: +$("temp_delta").value,
    nutrient_load: +$("nutrient_load").value,
    salinity_delta: +$("salinity_delta").value,
    seal_hunt: +$("seal_hunt").value,
    bird_hunt: +$("bird_hunt").value,
    noise: +$("noise").value,
    fishing: {
      sill: +$("f-sill").value, skarpsill: +$("f-skarpsill").value,
      spigg: +$("f-spigg").value, abborre: +$("f-abborre").value,
      gadda: +$("f-gadda").value, torsk: +$("f-torsk").value, lax: +$("f-lax").value,
      havsoring: +$("f-havsoring").value,
      smorbult: +$("f-smorbult").value, nejonoga: +$("f-nejonoga").value,
    },
  };
}
function setSliders(p) {
  $("years").value = p.years; $("temp_delta").value = p.temp_delta;
  $("nutrient_load").value = p.nutrient_load; $("salinity_delta").value = p.salinity_delta;
  $("seal_hunt").value = p.seal_hunt;
  if (p.bird_hunt != null) $("bird_hunt").value = p.bird_hunt;
  if (p.noise != null) $("noise").value = p.noise;
  $("f-sill").value = p.fishing.sill; $("f-skarpsill").value = p.fishing.skarpsill;
  $("f-spigg").value = p.fishing.spigg; $("f-torsk").value = p.fishing.torsk;
  if (p.fishing.abborre != null) $("f-abborre").value = p.fishing.abborre;
  if (p.fishing.gadda != null) $("f-gadda").value = p.fishing.gadda;
  if (p.fishing.lax != null) $("f-lax").value = p.fishing.lax;
  if (p.fishing.havsoring != null) $("f-havsoring").value = p.fishing.havsoring;
  if (p.fishing.smorbult != null) $("f-smorbult").value = p.fishing.smorbult;
  if (p.fishing.nejonoga != null) $("f-nejonoga").value = p.fishing.nejonoga;
  syncLabels();
}
function syncLabels() {
  $("v-temp").textContent = (+$("temp_delta").value).toFixed(1);
  $("v-nut").textContent = (+$("nutrient_load").value).toFixed(1);
  $("v-sal").textContent = (+$("salinity_delta").value).toFixed(1);
  $("v-seal").textContent = (+$("seal_hunt").value).toFixed(1);
  $("v-bird").textContent = (+$("bird_hunt").value).toFixed(1);
  $("v-noise").textContent = (+$("noise").value).toFixed(1);
  $("v-years").textContent = $("years").value;
  $("v-f-sill").textContent = $("f-sill").value;
  $("v-f-skarpsill").textContent = $("f-skarpsill").value;
  $("v-f-spigg").textContent = $("f-spigg").value;
  $("v-f-abborre").textContent = $("f-abborre").value;
  $("v-f-gadda").textContent = $("f-gadda").value;
  $("v-f-torsk").textContent = $("f-torsk").value;
  $("v-f-lax").textContent = $("f-lax").value;
  $("v-f-havsoring").textContent = $("f-havsoring").value;
  $("v-f-smorbult").textContent = $("f-smorbult").value;
  $("v-f-nejonoga").textContent = $("f-nejonoga").value;
}

// Nollställ scenario-slidern till "— eget —" (när man skruvar reglagen själv).
function scenarioToCustom() {
  const s = $("scenario"); if (s) s.value = 0;
  $("v-scenario").textContent = T("custom_scenario", "— eget —");
  $("scenario-desc").textContent = "";
}

// ---- Auto-kör: kör simuleringen strax efter att man ändrat ett reglage ----
let _autoTimer = null;
function autoRun() {
  clearTimeout(_autoTimer);
  _autoTimer = setTimeout(() => {
    scenarioToCustom();              // egna reglage, inte ett förval
    run(readParams());
  }, 300);                            // vänta tills man släpper/pausar draget
}

// ---- Kör simulering ----
let _runSeq = 0;   // sekvensnummer: bara det senaste svaret ritas (auto-kör)
async function run(body) {
  const myseq = ++_runSeq;
  $("run").disabled = true;
  $("status").textContent = "Simulerar… (löser ekvationerna)";
  try {
    const r = await fetch("/api/simulate", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body || readParams()),
    });
    const data = await r.json();
    if (myseq !== _runSeq) return;   // ett nyare anrop har startat → ignorera detta
    RES = data;
    $("time").max = RES.t.length - 1;
    ti = RES.t.length - 1;
    $("zone-name").textContent = RES.zone_names[selectedZone];
    buildChips();
    setTime(ti);
    drawAllCharts();
    $("status").textContent = `Klart — ${RES.t[RES.t.length-1].toFixed(0)} år. ${T("health_title","Hälsoindex")}: ${RES.health.index[RES.health.index.length-1].toFixed(0)}/100.`;
  } catch (e) {
    if (myseq === _runSeq) $("status").textContent = "Fel vid simulering: " + e;
  }
  if (myseq === _runSeq) $("run").disabled = false;
}

// ---- Spara / ladda ----
function currentSummary() {
  if (!RES) return {};
  const last = RES.t.length - 1;
  return { halsa_nu: RES.health.index[last] };
}
async function saveServer() {
  const namn = $("save-name").value.trim() || "Körning";
  await fetch("/api/saved", { method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ namn, user: currentUser, params: readParams(), summary: currentSummary() }) });
  loadSavedList();
}
function saveLocal() {
  const namn = $("save-name").value.trim() || "Körning";
  const arr = JSON.parse(localStorage.getItem("eystra_saved") || "[]");
  arr.push({ namn, params: readParams(), tid: new Date().toISOString().slice(0,16).replace("T"," ") });
  localStorage.setItem("eystra_saved", JSON.stringify(arr));
  loadSavedList();
}
async function loadSavedList() {
  let server = [];
  const q = currentUser ? "?user=" + encodeURIComponent(currentUser) : "";
  try { server = (await (await fetch("/api/saved" + q)).json()).sparade || []; } catch(e){}
  const local = JSON.parse(localStorage.getItem("eystra_saved") || "[]");
  const html = [];
  server.forEach(s => html.push(rowSaved(s.namn + " · server", s.params, "srv", s.id)));
  local.forEach((s,i) => html.push(rowSaved(s.namn + " · lokal", s.params, "loc", i)));
  $("saved-list").innerHTML = html.join("") || `<p class="hint">—</p>`;
  $("saved-list").querySelectorAll("[data-load]").forEach(b =>
    b.addEventListener("click", () => { setSliders(JSON.parse(b.dataset.params)); run(); }));
  $("saved-list").querySelectorAll("[data-del]").forEach(b =>
    b.addEventListener("click", async () => {
      const [kind, id] = b.dataset.del.split(":");
      if (kind === "srv") await fetch("/api/saved/" + id, { method:"DELETE" });
      else { const a = JSON.parse(localStorage.getItem("eystra_saved")||"[]"); a.splice(+id,1);
             localStorage.setItem("eystra_saved", JSON.stringify(a)); }
      loadSavedList();
    }));
}
function rowSaved(label, params, kind, id) {
  return `<div class="rep"><div class="rt">${escHtml(label)}</div><div>
    <button data-load="1" data-params='${escAttr(JSON.stringify(params))}'>${T("load","Ladda")}</button>
    <button data-del="${escAttr(kind + ":" + id)}">${T("delete","Ta bort")}</button></div></div>`;
}

// ---- AI: scenario + förklaring ----
async function aiScenario() {
  const text = $("ai-text").value.trim();
  if (!text) return;
  $("ai-run").disabled = true;
  $("ai-motiv").textContent = "AI tolkar…";
  try {
    const r = await fetch("/api/ai/scenario", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ text, current: readParams() }),
    });
    const p = await r.json();
    setSliders(p);
    const motiv = p.motivering ? `<div>${mdToHtml(p.motivering)}</div>` : "";
    $("ai-motiv").innerHTML = motiv + scenarioSettingsHtml(readParams());
    scenarioToCustom();
    await run(readParams());
  } catch (e) { $("ai-motiv").textContent = "AI-fel: " + e; }
  $("ai-run").disabled = false;
}

// Kompakt sammanställning av de inställningar AI:n satte (så man ser vad som gäller)
function scenarioSettingsHtml(p) {
  const disp = (DEF && DEF.display) || {};
  const f = p.fishing || {};
  const items = [
    [T("warming","Uppvärmning"), (+p.temp_delta).toFixed(1) + " °C"],
    [T("nutrient","Näring"), "×" + (+p.nutrient_load).toFixed(1)],
    [T("salinity","Salthalt"), (+p.salinity_delta).toFixed(1) + " PSU"],
    [T("seal_hunt","Säljakt"), (+p.seal_hunt).toFixed(1)],
    [T("bird_hunt","Skarv-/fågeljakt"), (+p.bird_hunt).toFixed(1)],
    [T("noise","Brus"), (+p.noise).toFixed(1)],
    [T("years","Antal år"), p.years],
  ].map(([k, v]) => `<b>${k}:</b> ${v}`).join(" · ");
  const fish = ["sill","skarpsill","spigg","abborre","gadda","smorbult","torsk","lax","havsoring","nejonoga"]
    .filter(k => f[k] != null)
    .map(k => `${disp[k] || k} ${(+f[k]).toFixed(2)}`).join(", ");
  return `<div class="ai-settings">⚙️ ${items}<br><b>${T("fishing_pressure","Fisketryck")}:</b> ${fish}</div>`;
}
async function explain() {
  if (!RES) return;
  $("explain").disabled = true;
  $("ai-explain").textContent = "Ekologen tänker…";
  const start = {}, end = {}, bottom = {};
  const last = RES.t.length - 1;
  RES.compartments.forEach(c => {
    start[RES.display[c]] = +RES.totals[c][0].toFixed(2);
    end[RES.display[c]] = +RES.totals[c][last].toFixed(2);
  });
  RES.zones.forEach(z => bottom[RES.zone_names[z]] = +RES.series[z].O2b[last].toFixed(1));
  const summary = { period: `år ${BASE_YEAR}–${BASE_YEAR + RES.t[last]}`,
                    inställningar: readParams(), start, slut: end, bottensyre_per_zon: bottom,
                    hälsoindex: RES.health.index[RES.health.index.length-1] };
  try {
    const r = await fetch("/api/ai/explain", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ summary }),
    });
    const d = await r.json();
    $("ai-explain").innerHTML = mdToHtml(d.text || d.error || "");
  } catch (e) { $("ai-explain").textContent = "AI-fel: " + e; }
  $("explain").disabled = false;
}

// ---- Monte Carlo ----
async function runMC() {
  $("mc-run").disabled = true;
  $("mc-status").textContent = "Kör Monte Carlo… detta tar ~30–60 sekunder (många simuleringar parallellt).";
  const p = readParams();
  try {
    const r = await fetch("/api/montecarlo", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ draws: +$("mc-draws").value, temp_delta: p.temp_delta,
                             nutrient_load: p.nutrient_load, salinity_delta: p.salinity_delta }),
    });
    MC = await r.json();
    renderMC();
    fillEco();
    $("mc-status").textContent = `Klart — ${MC.n_draws} lottningar × ${MC.strategier.length} strategier.`
      + (MC.cachad ? " ⚡ (hämtad ur cache — inga nya beräkningar)" : "");
  } catch (e) { $("mc-status").textContent = "Fel: " + e; }
  $("mc-run").disabled = false;
}
function renderMC() {
  $("mc-results").style.display = "";
  const H = MC.horisonter;
  const bestKey = MC.basta[String(H[H.length-1])];
  const best = MC.resultat[bestKey];
  $("mc-best").innerHTML = `Bäst återhämtning på sikt: <b>${best.namn}</b> — ${T("health_title","hälsoindex")} `
    + `${best.halsa[H[H.length-1]].mean}/100 vid ${H[H.length-1]} år.`
    + `<div class="hint" style="margin-top:6px">👉 ${T("mc_click_hint","Klicka på en strategi i tabellen för att ladda in dess värden i simuleringen och analysera resultatet.")}</div>`;

  const dagens = (DEF && DEF.dagens_halsa) ? DEF.dagens_halsa.index : null;
  let html = `<thead><tr><th>${T("strategy","Strategi")}</th>`
           + `<th>${T("today_health","Dagens hälsa")}</th>`;
  H.forEach(h => html += `<th>${h} år</th>`);
  html += `<th></th></tr></thead><tbody>`;
  MC.strategier.forEach(st => {
    const row = MC.resultat[st.key];
    html += `<tr class="strat-row" data-strat="${st.key}" title="Klicka för att ladda in i simuleringen"><td>${row.namn}</td>`;
    html += `<td class="today-cell"><b>${dagens != null ? dagens : "—"}</b></td>`;
    H.forEach(h => {
      const cell = row.halsa[h];
      const isBest = MC.basta[String(h)] === st.key;
      html += `<td${isBest ? ' class="best-cell"' : ''}><b>${cell.mean}</b>`
            + `<div class="band">${cell.p10}–${cell.p90}</div></td>`;
    });
    html += `<td class="load-cell">▶ ${T("load","Ladda")}</td></tr>`;
  });
  html += "</tbody>";
  $("mc-table").innerHTML = html;
  $("mc-table").querySelectorAll(".strat-row").forEach(tr =>
    tr.addEventListener("click", () => applyStrategy(tr.dataset.strat)));

  const maxc = Math.max(...MC.kanslighet.map(k => Math.abs(k.korrelation)), 0.01);
  $("mc-sensitivity").innerHTML = MC.kanslighet.map(k => `
    <div class="sens-row">
      <span class="name">${k.namn}</span>
      <span class="track"><span class="fill" style="width:${Math.abs(k.korrelation)/maxc*100}%"></span></span>
      <span class="num">${k.korrelation >= 0 ? "+" : ""}${k.korrelation}</span>
      <span class="src">${k.source}</span>
    </div>`).join("");
}

// ---- Ekonomi ----
function fillEco() {
  if (!MC) return;
  const es = $("eco-strategy"), eh = $("eco-horizon");
  es.innerHTML = MC.strategier.map(s => `<option value="${s.key}">${s.namn}</option>`).join("");
  eh.innerHTML = MC.horisonter.map(h => `<option value="${h}">${h} år</option>`).join("");
  es.value = MC.basta[String(MC.horisonter[MC.horisonter.length-1])];
  eh.value = MC.horisonter[MC.horisonter.length-1];
  renderEco();
}
function renderEco() {
  if (!MC) return;
  $("eco-status").textContent = "";
  const sk = $("eco-strategy").value, h = $("eco-horizon").value;
  const row = MC.resultat[sk];
  const val = row.varde[h].per_land, imp = row.forbattring[h].per_land;
  let html = `<thead><tr><th>${T("country","Land")}</th><th>${T("fishing_col","Fiske")}</th><th>${T("services_col","Ekosystemtjänster")}</th><th>${T("total_col","Totalt")}</th><th>${T("improvement_col","Förbättring")}</th></tr></thead><tbody>`;
  MC.lander.forEach(land => {
    const v = val[land], d = imp[land];
    const cls = d > 0.5 ? "pos" : d < -0.5 ? "neg" : "";
    html += `<tr><td>${land}</td><td>${v.fiske}</td><td>${v.tjanster}</td><td><b>${v.total}</b></td>`
          + `<td class="${cls}">${d > 0 ? "+" : ""}${d}</td></tr>`;
  });
  html += `<tr class="best-row"><td><b>${T("whole_sea","Hela Östersjön")}</b></td><td></td><td></td>`
        + `<td><b>${row.varde[h].total_hav}</b></td><td class="${row.forbattring[h].total_hav>0?'pos':'neg'}">`
        + `${row.forbattring[h].total_hav>0?'+':''}${row.forbattring[h].total_hav}</td></tr>`;
  html += "</tbody>";
  $("eco-table").innerHTML = html;
}

// ---- Forskningsförslag + rapportförslag (AI) ----
async function runResearch() {
  if (!MC) { $("research-out").textContent = "Kör Monte Carlo först."; return; }
  $("research-run").disabled = true;
  $("research-out").textContent = "AI:n analyserar kunskapsluckorna…";
  try {
    const r = await fetch("/api/ai/research", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ kanslighet: MC.kanslighet, basta: MC.basta }),
    });
    $("research-out").innerHTML = mdToHtml((await r.json()).text || "");
  } catch (e) { $("research-out").textContent = "AI-fel: " + e; }
  $("research-run").disabled = false;
}
async function suggestReports() {
  $("suggest-reports").disabled = true;
  $("suggest-out").textContent = "AI:n letar efter relevanta rapporter…";
  try {
    const r = await fetch("/api/ai/suggest-reports", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ kanslighet: MC ? MC.kanslighet : null }),
    });
    $("suggest-out").innerHTML = mdToHtml((await r.json()).text || "");
  } catch (e) { $("suggest-out").textContent = "AI-fel: " + e; }
  $("suggest-reports").disabled = false;
}

// ---- Verifiering ----
async function runVerify() {
  $("verify-run").disabled = true;
  $("verify-status").textContent = "Kör kontrollerna… (~20 sekunder)";
  try {
    const v = await (await fetch("/api/verify")).json();
    $("verify-status").textContent = `${v.godkanda} av ${v.antal} kontroller godkända.`;
    $("verify-list").innerHTML = v.kontroller.map(c => `
      <div class="check ${c.godkand ? 'ok' : 'fail'}">
        <span class="mark">${c.godkand ? '✓' : '✗'}</span><b>${c.namn}</b>
        <div class="meta">${c.observerat} · förväntat: ${c.forvantat}</div>
        <div class="meta">${c.forklaring}</div>
        <div class="meta">Källa: ${c.source}</div>
      </div>`).join("");
  } catch (e) { $("verify-status").textContent = "Fel: " + e; }
  $("verify-run").disabled = false;
}

// ---- Ekologisk beroendematris ----
const ECO_GROUP_COLOR = {
  naring: "#8b6f47", detritus: "#7a6a55", producent: "#4ade80",
  primarkonsument: "#22d3aa", planktivor: "#38bdf8", bottenfisk: "#2dd4bf",
  kustrovfisk: "#818cf8", rovfisk: "#a78bfa", toppredator: "#f472b6",
};
function renderMatrix() {
  const el = $("eco-matrix");
  if (!el || !DEF || !DEF.ekologi) return;
  const E = DEF.ekologi;
  const ord = E.order, M = E.matris, disp = E.display, grp = E.grupp, emoji = E.emoji || {};
  const shortName = c => `${emoji[c] || ""} ${disp[c] || c}`.trim();
  const depOn = T("eco_depends", "beror på");
  let h = `<table class="eco-mtx"><thead><tr><th class="corner">${T("eco_row_consumer","Konsument \\ Resurs")}</th>`;
  ord.forEach(c => {
    h += `<th class="col" style="--g:${ECO_GROUP_COLOR[grp[c]] || "#888"}" title="${escAttr(disp[c])}">${escHtml(emoji[c] || "")}<span>${escHtml(disp[c])}</span></th>`;
  });
  h += `</tr></thead><tbody>`;
  ord.forEach((r, i) => {
    h += `<tr><th class="rowh" style="--g:${ECO_GROUP_COLOR[grp[r]] || "#888"}">${escHtml(shortName(r))}</th>`;
    ord.forEach((c, j) => {
      const w = M[i][j] || 0;
      if (i === j) { h += `<td class="diag"></td>`; return; }
      if (!w) { h += `<td></td>`; return; }
      const a = (0.18 + 0.82 * Math.min(w, 1)).toFixed(2);
      const tip = `${disp[r]} ${depOn} ${disp[c]} — ${w.toFixed(2)}`;
      h += `<td class="cell" style="background:rgba(46,160,67,${a})" title="${escAttr(tip)}">${w >= 0.5 ? "●" : ""}</td>`;
    });
    h += `</tr>`;
  });
  h += `</tbody></table>`;
  el.innerHTML = h;

  // Grupp-legend
  const leg = $("eco-legend");
  if (leg) {
    leg.innerHTML = Object.keys(E.grupp_namn || {}).map(g =>
      `<span class="eco-lg"><span class="sw" style="background:${ECO_GROUP_COLOR[g] || "#888"}"></span>${escHtml(E.grupp_namn[g])}</span>`
    ).join("");
  }
  renderSalt();
}
function renderSalt() {
  const el = $("eco-salt");
  if (!el || !DEF || !DEF.ekologi || !DEF.ekologi.salt) return;
  const E = DEF.ekologi, salt = E.salt, disp = E.display, emoji = E.emoji || {};
  const MAXP = 20; // PSU-skala 0..20 (norr→söder)
  const rows = Object.keys(salt).map(c => {
    const o = salt[c], opt = o.opt, wdt = o.width;
    const lo = Math.max(0, opt - wdt), hi = Math.min(MAXP, opt + wdt);
    const L = (lo / MAXP * 100).toFixed(1), W = ((hi - lo) / MAXP * 100).toFixed(1);
    const C = (opt / MAXP * 100).toFixed(1);
    return `<div class="salt-row"><div class="salt-lbl">${escHtml((emoji[c]||"") + " " + (disp[c]||c))}</div>
      <div class="salt-track"><div class="salt-band" style="left:${L}%;width:${W}%"></div>
      <div class="salt-mark" style="left:${C}%" title="optimum ${opt} PSU"></div></div></div>`;
  }).join("");
  el.innerHTML = `<div class="salt-scale"><span>0 PSU (${T("north","norr")})</span><span>10</span><span>20 PSU (${T("south","söder")})</span></div>${rows}`;
}

// ---- Publikationer/rapporter (lösenordsskyddad hantering, F-02) ----
// Att lägga till/ta bort publikationer kräver lösenordet "abborre". Vi frågar en
// gång per session och skickar det som header. Vid fel nollställs det för nytt försök.
let adminPw = "";
function askAdminPw() {
  if (!adminPw) adminPw = (window.prompt(T("pw_prompt", "Lösenord för att hantera publikationer:")) || "").trim();
  return adminPw;
}
function adminHeaders(extra) {
  return Object.assign({ "X-Admin-Password": askAdminPw() }, extra || {});
}
async function loadReports() {
  const d = await (await fetch("/api/reports")).json();
  const list = d.rapporter || [];
  $("rep-list").innerHTML = list.length ? list.map(r => {
    const lank = (r.lank && /^https?:\/\//i.test(r.lank)) ? r.lank : "";
    const lankBtn = lank
      ? `<a class="rep-link" href="${escAttr(lank)}" target="_blank" rel="noopener">${T("open_link","Länk »")}</a>`
      : "";
    return `<div class="rep">
      <div><div class="rt">${escHtml(r.titel)}</div><div class="rm">${escHtml(r.tillagd)} · ${r.tecken|0} tecken · ${escHtml(r.utdrag)}…</div></div>
      <div class="rep-actions">${lankBtn}<button data-del="${r.id|0}">${T("delete","Ta bort")}</button></div>
    </div>`;
  }).join("") : `<p class="hint">Inga rapporter inlagda ännu.</p>`;
  $("rep-list").querySelectorAll("button[data-del]").forEach(b =>
    b.addEventListener("click", async () => {
      const resp = await fetch("/api/reports/" + b.dataset.del, { method: "DELETE", headers: adminHeaders() });
      if (resp.status === 403) { adminPw = ""; $("rep-status").textContent = T("pw_wrong", "Fel lösenord."); return; }
      loadReports();
    }));
}
async function addReport() {
  const titel = $("rep-title").value.trim(), text = $("rep-text").value.trim();
  const lank = ($("rep-link") ? $("rep-link").value.trim() : "");
  if (!text) { $("rep-status").textContent = "Klistra in text först."; return; }
  $("rep-add").disabled = true;
  const resp = await fetch("/api/reports", {
    method: "POST", headers: adminHeaders({"Content-Type":"application/json"}),
    body: JSON.stringify({ titel, text, lank }),
  });
  const r = await resp.json();
  if (resp.status === 403) { adminPw = ""; $("rep-status").textContent = r.error || T("pw_wrong", "Fel lösenord."); }
  else if (r.ok) { $("rep-title").value = ""; $("rep-text").value = ""; if ($("rep-link")) $("rep-link").value = "";
    $("rep-status").textContent = "Tillagd. AI:n väger nu in den."; loadReports(); }
  else $("rep-status").textContent = r.error || "Fel.";
  $("rep-add").disabled = false;
}

// ---- Idélåda ----
async function loadIdeas() {
  const d = await (await fetch("/api/ideas")).json();
  const list = d.ideer || [];
  $("idea-list").innerHTML = list.length ? list.map(i => `
    <div class="rep"><div><div class="rt">${escHtml(i.text)}</div>
      <div class="rm">— ${escHtml(i.namn)} · ${escHtml(i.tid)}</div></div>
      <button data-del="${i.id|0}">${T("delete","Ta bort")}</button></div>`).join("")
    : `<p class="hint">Inga idéer ännu — bli först!</p>`;
  $("idea-list").querySelectorAll("button[data-del]").forEach(b =>
    b.addEventListener("click", async () => {
      const resp = await fetch("/api/ideas/" + b.dataset.del, { method:"DELETE", headers: adminHeaders() });
      if (resp.status === 403) { adminPw = ""; $("idea-status").textContent = T("pw_wrong", "Fel lösenord."); return; }
      loadIdeas(); }));
}
async function addIdea() {
  const namn = $("idea-name").value.trim(), text = $("idea-text").value.trim();
  if (!text) { $("idea-status").textContent = "Skriv en idé först."; return; }
  $("idea-add").disabled = true;
  const r = await (await fetch("/api/ideas", { method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ namn, text }) })).json();
  if (r.ok) { $("idea-text").value = ""; $("idea-status").textContent = "Tack! Idén är inskickad."; loadIdeas(); }
  else $("idea-status").textContent = r.error || "Fel.";
  $("idea-add").disabled = false;
}

// ---- Export ----
function buildExportSummary() {
  if (!RES) return null;
  const last = RES.t.length - 1;
  const params = readParams();
  const p_labels = {
    "Klimat (°C)": params.temp_delta, "Näring (×)": params.nutrient_load,
    "Salthalt (PSU)": params.salinity_delta, "Säljakt": params.seal_hunt,
    "Skarvjakt": params.bird_hunt, "Brus": params.noise, "År": params.years,
    "Fiske torsk": params.fishing.torsk,
  };
  const arter = RES.compartments.filter(c => !["O2","O2b","N","det"].includes(c)).map(c => ({
    namn: RES.display[c], start: +RES.totals[c][0].toFixed(2),
    slut: +RES.totals[c][last].toFixed(2), enhet: DEF.units[c],
  }));
  const trofiLast = {};
  if (RES.trofi) { const li = RES.trofi.years.length - 1;
    RES.trofi.ordning.forEach(n => trofiLast[n] = RES.trofi.nivaer[n][li]); }
  const uttakLast = {};
  if (RES.uttak) { const li = RES.uttak.years.length - 1;
    ["fiske","sal","skarv","atervinning"].forEach(k => { if (RES.uttak[k]) uttakLast[k] = RES.uttak[k][li]; }); }
  const summary = {
    parametrar: p_labels, halsa_nu: RES.health.index[last],
    arter, trofi: { nivaer_slut: trofiLast }, uttak_slut: uttakLast,
  };
  if (MC) {
    const h = MC.horisonter[MC.horisonter.length-1];
    const bestKey = MC.basta[String(h)];
    summary.mc = { basta_namn: MC.resultat[bestKey].namn,
                   ekonomi_per_land: MC.resultat[bestKey].forbattring[h].per_land };
  }
  return summary;
}
const MODE_DESC = {
  nyfiken:  ["mode_nyfiken_desc",  "Enkelt och kort, utan fackspråk — för dig som är nyfiken på havet."],
  generell: ["mode_generell_desc", "Allmän, saklig rapport om körningens resultat."],
  politik:  ["mode_politik_desc",  "Beslutsunderlag: strategier, argument, investeringar och samhällsvärden. Ekonomin visas i både euro och lokal valuta."],
  forskare: ["mode_forskare_desc", "Fördjupning: mekanismer och samband, osäkerheter och kunskapsluckor, samt nästa steg i forskningen."],
};
function updateModeDesc() {
  const sel = $("exp-mode"), out = $("exp-mode-desc");
  if (!sel || !out) return;
  const d = MODE_DESC[sel.value] || MODE_DESC.generell;
  out.textContent = T(d[0], d[1]);
}
async function runExport() {
  const summary = buildExportSummary();
  if (!summary) { $("exp-status").textContent = T("run_first","Kör en simulering först."); return; }
  $("exp-run").disabled = true;
  $("exp-status").textContent = "Skapar dokument…";
  try {
    const r = await fetch("/api/export", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ format: $("exp-format").value, lang: $("exp-lang").value,
        mode: $("exp-mode").value,
        recipient: $("exp-recipient").value.trim(), summary, ai_text: $("exp-ai").checked }) });
    if (!r.ok) { $("exp-status").textContent = (await r.json()).error || "Fel."; $("exp-run").disabled = false; return; }
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename=([^;]+)/);
    const name = m ? m[1].replace(/"/g,"") : "eystrasalt";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
    $("exp-status").textContent = "Klart — filen laddades ned: " + name;
  } catch (e) { $("exp-status").textContent = "Fel: " + e; }
  $("exp-run").disabled = false;
}
function openMail() {
  const rec = $("exp-recipient").value.trim();
  const to = /@/.test(rec) ? rec : "";
  const subj = encodeURIComponent("Eystrasalt — Östersjörapport");
  const hn = RES ? RES.health.index[RES.health.index.length-1] : "";
  const body = encodeURIComponent(`Hej${rec && !to ? " " + rec : ""},\n\nHär kommer en rapport från Eystrasalt-simuleringen. Ekosystemets hälsoindex: ${hn}/100.\n\n(Bifoga det nedladdade dokumentet.)\n\nMvh`);
  window.location.href = `mailto:${to}?subject=${subj}&body=${body}`;
}

// ---- Dela webappen (länk / sociala medier / e-post) ----
function shareUrl() {
  // Dela nuvarande scenario: koda reglagen i ?s= så mottagaren öppnar samma läge
  let base = location.origin + location.pathname;
  try {
    const s = btoa(unescape(encodeURIComponent(JSON.stringify(readParams()))));
    return base + "?s=" + s;
  } catch (e) { return base; }
}
function shareText() {
  const hn = DEF && DEF.dagens_halsa ? DEF.dagens_halsa.index : "";
  return `Eystrasalt — en öppen digital tvilling för Östersjön. Kör dina egna simuleringar av havets framtid! Dagens hälsoindex: ${hn}/100.`;
}
function doShare(kind) {
  const url = shareUrl(), u = encodeURIComponent(url), t = encodeURIComponent(shareText());
  let win = null;
  if (kind === "copy") {
    navigator.clipboard && navigator.clipboard.writeText(url)
      .then(() => $("share-copied").textContent = T("copied","Länk kopierad!"))
      .catch(() => $("share-copied").textContent = url);
    return;
  }
  if (kind === "native") {
    if (navigator.share) navigator.share({ title: "Eystrasalt", text: shareText(), url });
    else $("share-copied").textContent = T("share_native_unsupported","Enhetsdelning stöds ej — kopiera länken istället.");
    return;
  }
  if (kind === "email") win = `mailto:?subject=${encodeURIComponent("Eystrasalt — Östersjön")}&body=${t}%0A%0A${u}`;
  if (kind === "facebook") win = `https://www.facebook.com/sharer/sharer.php?u=${u}`;
  if (kind === "x") win = `https://twitter.com/intent/tweet?url=${u}&text=${t}`;
  if (kind === "linkedin") win = `https://www.linkedin.com/sharing/share-offsite/?url=${u}`;
  if (kind === "whatsapp") win = `https://wa.me/?text=${t}%20${u}`;
  if (win) window.open(win, kind === "email" ? "_self" : "_blank");
}
function setupShare() {
  const btn = $("share-btn"), menu = $("share-menu");
  btn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; $("share-copied").textContent = ""; });
  menu.querySelectorAll("[data-share]").forEach(b =>
    b.addEventListener("click", (e) => { e.stopPropagation(); doShare(b.dataset.share); }));
  document.addEventListener("click", () => { menu.hidden = true; });
}

// ---- Enkel användare (lösenordslös profil) ----
function renderUser() {
  const lbl = $("user-label");
  lbl.innerHTML = currentUser
    ? `${T("active_user","Aktiv användare")}: <b>${escHtml(currentUser)}</b>`
    : T("no_user","Ingen användare vald — dina serverkörningar sparas öppet.");
  $("user-name").value = currentUser;
}
function setUser() {
  currentUser = $("user-name").value.trim().slice(0, 60);
  localStorage.setItem("eystra_user", currentUser);
  renderUser(); loadSavedList();
}

// ---- Dagens hälsa (baslinjen) ----
// Visas numera som första kolumn i Monte Carlo-tabellen (se renderMC).
function renderTodayHealth() {
  const el = $("today-health");
  if (!el || !DEF || !DEF.dagens_halsa) return;
  const v = DEF.dagens_halsa.index;
  const col = v >= 66 ? "var(--good)" : v >= 40 ? "var(--warn)" : "var(--bad)";
  el.innerHTML = `🩺 ${T("today_health","Dagens hälsa")}: <b style="color:${col}">${v}/100</b>`;
}

// ---- Tala-till-text (webbläsarens Web Speech API, funkar i Chrome) ----
function setupMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = $("idea-mic");
  if (!btn) return;
  if (!SR) { btn.disabled = true; btn.title = T("mic_unsupported","Stöds ej"); return; }
  btn.addEventListener("click", () => {
    if (recognizing) { recognition && recognition.stop(); return; }
    recognition = new SR();
    recognition.lang = LOCALE[$("lang").value] || "sv-SE";
    recognition.interimResults = true;
    recognition.continuous = true;
    let base = $("idea-text").value;
    recognition.onstart = () => { recognizing = true; btn.classList.add("rec");
      $("mic-status").textContent = T("mic_listening","🎤 Lyssnar…"); };
    recognition.onerror = (e) => { $("mic-status").textContent = "🎤 " + e.error; };
    recognition.onend = () => { recognizing = false; btn.classList.remove("rec");
      if (!$("mic-status").textContent.startsWith("🎤 ")) {} $("mic-status").textContent = ""; };
    recognition.onresult = (ev) => {
      let fin = "", interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const tr = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) fin += tr; else interim += tr;
      }
      if (fin) base = (base ? base + " " : "") + fin.trim();
      $("idea-text").value = (base + (interim ? " " + interim : "")).trim();
    };
    recognition.start();
  });
}

// ---- Tooltips ----
function buildTooltips() {
  document.querySelectorAll(".help").forEach(el => {
    if (el.dataset.built) return;
    const txt = DEF.help[el.dataset.k];
    if (!txt) return;
    const tip = document.createElement("span");
    tip.className = "tip"; tip.textContent = txt;
    el.appendChild(tip); el.dataset.built = "1";
    el.addEventListener("click", (e) => { e.stopPropagation(); el.classList.toggle("show"); });
  });
  document.addEventListener("click", () =>
    document.querySelectorAll(".help.show").forEach(h => h.classList.remove("show")));
}

// ---- Flikar ----
function activateTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  $("view-" + name).classList.add("active");
  if (name === "reports") loadReports();
  if (name === "ideas") loadIdeas();
  if (name === "politik") renderPolitik();
  if (name === "ekologi") renderMatrix();
  if (name === "pyramid" && RES) { drawPyramid(); drawUttak(); drawTrofi(); }
}
function initTabs() {
  document.querySelectorAll(".tab").forEach(tab =>
    tab.addEventListener("click", () => activateTab(tab.dataset.tab)));
}

// ---- Ladda in en strategi i simuleringen (klick i MC-tabellen) ----
function applyStrategy(key) {
  if (!MC) return;
  const strat = MC.strategier.find(s => s.key === key);
  if (!strat) return;
  const ov = strat.params || {};
  const k = MC.kontext || {};
  const baseFish = (DEF.baseline && DEF.baseline.fishing) || {};
  // Strategin = standardfiske + strategins överlagringar, i MC:ns stress-kontext
  const p = {
    years: +$("years").value,
    temp_delta: k.temp_delta != null ? k.temp_delta : +$("temp_delta").value,
    salinity_delta: k.salinity_delta != null ? k.salinity_delta : +$("salinity_delta").value,
    nutrient_load: ov.nutrient_load != null ? ov.nutrient_load
                   : (k.nutrient_load != null ? k.nutrient_load : 1.0),
    seal_hunt: +$("seal_hunt").value,
    bird_hunt: +$("bird_hunt").value,
    noise: +$("noise").value,
    fishing: { ...baseFish, ...(ov.fishing || {}) },
  };
  setSliders(p);
  activateTab("sim");
  scenarioToCustom();
  $("status").textContent = `Laddar in strategin "${strat.namn}"…`;
  run(p);
}

// ---- Init ----
async function init() {
  DEF = await (await fetch("/api/defaults")).json();

  // Språkväljare: flaggor högst upp (momentant byte) + dold select som fallback.
  const lsel = $("lang");
  DEF.langs.forEach(l => lsel.innerHTML += `<option value="${l.code}">${l.native}</option>`);
  buildFlags(DEF.langs);
  const saved = localStorage.getItem("eystra_lang") || "sv";
  lsel.value = saved;
  await loadLang(saved);
  lsel.addEventListener("change", () => loadLang(lsel.value));

  // Export-språk (samma lista)
  const el = $("exp-lang");
  DEF.langs.forEach(l => el.innerHTML += `<option value="${l.code}">${l.native}</option>`);
  el.value = saved;

  // Donationsknappar
  document.querySelectorAll("#donate-btn, #donate-link").forEach(a => { if (a) a.href = donateHref(); });

  // Export-läge: beskrivning uppdateras vid byte (och vid språkbyte via refreshDynamic)
  const modeSel = $("exp-mode");
  if (modeSel) { modeSel.addEventListener("change", updateModeDesc); updateModeDesc(); }

  buildTooltips();
  initTabs();

  // Scenario är nu ett stress-reglage (slider): position 0 = eget, 1..N = förval.
  const sc = $("scenario");
  sc.max = DEF.scenarios.length;
  sc.addEventListener("input", () => {
    const i = +sc.value;
    if (i === 0) { scenarioToCustom(); run(readParams()); return; }
    const s = DEF.scenarios[i - 1];
    $("v-scenario").textContent = s.namn;
    $("scenario-desc").textContent = s.beskrivning;
    setSliders(s.reglage);      // scenariot ställer in de andra stress-reglagen
    run(readParams());          // kör med scenariots reglagevärden
  });

  const lay = $("layer");
  LAYERS.forEach(l => lay.innerHTML += `<option value="${l.key}">${l.label}</option>`);
  lay.value = "pie";
  lay.addEventListener("change", updateMap);

  // #scenario har egen hanterare (ovan) — uteslut den ur de generiska lyssnarna.
  document.querySelectorAll('#view-sim input[type=range]:not(#scenario)').forEach(r =>
    r.addEventListener("input", syncLabels));
  // Auto-kör när något stress-/fiskereglage ändras (interaktivt, ingen AI).
  // #time (tidslinjen) ligger utanför .controls och triggar inte omkörning.
  document.querySelectorAll('.controls input[type=range]:not(#scenario)').forEach(r =>
    r.addEventListener("input", autoRun));
  // Reglage-beteende (klick prick=standard, klick sida=steg, dra=flytta) på alla
  // reglage i kontrollpanelen inkl. scenario (tidslinjen #time berörs ej).
  document.querySelectorAll('.controls input[type=range]').forEach(enhanceSlider);
  syncLabels();

  $("run").addEventListener("click", () => { scenarioToCustom(); run(); });
  $("play").addEventListener("click", play);
  $("time").addEventListener("input", e => { if (RES) setTime(+e.target.value); });
  // Klick i huvudgrafen → hoppa till det året (kartan/regionerna uppdateras)
  $("chart-main").addEventListener("click", chartSeek);
  $("ai-run").addEventListener("click", aiScenario);
  $("explain").addEventListener("click", explain);
  $("save-server").addEventListener("click", saveServer);
  $("save-local").addEventListener("click", saveLocal);

  document.querySelectorAll(".presets button[data-preset]").forEach(b =>
    b.addEventListener("click", () => {
      selectedSeries = new Set(PRESETS[b.dataset.preset]);
      buildChips(); drawMainChart();
    }));
  $("normalize").checked = true;
  $("normalize").addEventListener("change", drawMainChart);

  $("mc-draws").addEventListener("input", () => $("v-mc-draws").textContent = $("mc-draws").value);
  $("mc-run").addEventListener("click", runMC);
  $("research-run").addEventListener("click", runResearch);
  $("suggest-reports").addEventListener("click", suggestReports);
  $("eco-strategy").addEventListener("change", renderEco);
  $("eco-horizon").addEventListener("change", renderEco);
  $("verify-run").addEventListener("click", runVerify);
  $("rep-add").addEventListener("click", addReport);
  $("idea-add").addEventListener("click", addIdea);
  setupMic();
  $("exp-run").addEventListener("click", runExport);
  $("exp-mail").addEventListener("click", openMail);

  $("share-btn") && setupShare();
  $("user-set").addEventListener("click", setUser);
  renderUser();
  renderTodayHealth();

  buildMap();
  selectZone(selectedZone);
  loadSavedList();

  // Delad länk? Läs in scenariot ur ?s= och kör det
  const shared = new URLSearchParams(location.search).get("s");
  if (shared) {
    try {
      const p = JSON.parse(decodeURIComponent(escape(atob(shared))));
      setSliders(p);
      await run(p);
      return;
    } catch (e) { /* ogiltig länk → kör baslinje */ }
  }
  await run();
}

init();
