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
  gadda:"#4d7c0f", torsk:"#ff6b6b", lax:"#fb7185", fagel:"#e879f9", sal:"#c084fc",
  O2:"#7dd3fc", O2b:"#2563eb", det:"#8aa9c4",
};
// Färgpalett för uttag och trofinivåer
const UCOL = { fiske:"#ff6b6b", sal:"#c084fc", skarv:"#e879f9", atervinning:"#4ade80" };
const TROFI_COL = ["#9fb3c8","#4ade80","#33c2c2","#4ea8ff","#a3e635","#ff6b6b","#e879f9","#8aa9c4"];
// Levande biomassa som visas i kartans tårtdiagram (uteslut näring/syre/detritus)
const BIOMASS = ["phyto","cyano","zoo","bentos","sill","skarpsill","spigg","abborre","gadda","torsk","lax","fagel","sal"];

const PRESETS = {
  plankton: ["N","phyto","cyano","zoo"],
  fisk: ["sill","skarpsill","spigg","abborre","gadda","torsk","lax"],
  botten: ["bentos","O2b","det"],
  syre: ["O2","O2b"],
  allt: ["N","phyto","cyano","zoo","bentos","sill","skarpsill","spigg","abborre","gadda","torsk","lax","fagel","sal","O2","O2b"],
};

const $ = (id) => document.getElementById(id);
const T = (k, fallback) => STR[k] || fallback || k;
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
async function loadLang(code) {
  try {
    STR = await (await fetch("/api/i18n/" + code)).json();
  } catch (e) { STR = {}; }
  applyI18n();
  localStorage.setItem("eystra_lang", code);
  document.documentElement.lang = code;
}
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const k = el.dataset.i18n; if (STR[k]) el.textContent = STR[k];
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    const k = el.dataset.i18nPh; if (STR[k]) el.placeholder = STR[k];
  });
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
  return `<div class="rep"><div class="rt">${label}</div><div>
    <button data-load="1" data-params='${JSON.stringify(params)}'>${T("load","Ladda")}</button>
    <button data-del="${kind}:${id}">${T("delete","Ta bort")}</button></div></div>`;
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
  const fish = ["sill","skarpsill","spigg","abborre","gadda","torsk","lax"]
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

// ---- Rapporter ----
async function loadReports() {
  const d = await (await fetch("/api/reports")).json();
  const list = d.rapporter || [];
  $("rep-list").innerHTML = list.length ? list.map(r => `
    <div class="rep">
      <div><div class="rt">${r.titel}</div><div class="rm">${r.tillagd} · ${r.tecken} tecken · ${r.utdrag}…</div></div>
      <button data-del="${r.id}">${T("delete","Ta bort")}</button>
    </div>`).join("") : `<p class="hint">Inga rapporter inlagda ännu.</p>`;
  $("rep-list").querySelectorAll("button[data-del]").forEach(b =>
    b.addEventListener("click", async () => {
      await fetch("/api/reports/" + b.dataset.del, { method: "DELETE" });
      loadReports();
    }));
}
async function addReport() {
  const titel = $("rep-title").value.trim(), text = $("rep-text").value.trim();
  if (!text) { $("rep-status").textContent = "Klistra in text först."; return; }
  $("rep-add").disabled = true;
  const r = await (await fetch("/api/reports", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ titel, text }),
  })).json();
  if (r.ok) { $("rep-title").value = ""; $("rep-text").value = "";
    $("rep-status").textContent = "Tillagd. AI:n väger nu in den."; loadReports(); }
  else $("rep-status").textContent = r.error || "Fel.";
  $("rep-add").disabled = false;
}

// ---- Idélåda ----
async function loadIdeas() {
  const d = await (await fetch("/api/ideas")).json();
  const list = d.ideer || [];
  $("idea-list").innerHTML = list.length ? list.map(i => `
    <div class="rep"><div><div class="rt">${i.text}</div>
      <div class="rm">— ${i.namn} · ${i.tid}</div></div>
      <button data-del="${i.id}">${T("delete","Ta bort")}</button></div>`).join("")
    : `<p class="hint">Inga idéer ännu — bli först!</p>`;
  $("idea-list").querySelectorAll("button[data-del]").forEach(b =>
    b.addEventListener("click", async () => {
      await fetch("/api/ideas/" + b.dataset.del, { method:"DELETE" }); loadIdeas(); }));
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
async function runExport() {
  const summary = buildExportSummary();
  if (!summary) { $("exp-status").textContent = T("run_first","Kör en simulering först."); return; }
  $("exp-run").disabled = true;
  $("exp-status").textContent = "Skapar dokument…";
  try {
    const r = await fetch("/api/export", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ format: $("exp-format").value, lang: $("exp-lang").value,
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
    ? `${T("active_user","Aktiv användare")}: <b>${currentUser}</b>`
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

  // Språkväljare
  const lsel = $("lang");
  DEF.langs.forEach(l => lsel.innerHTML += `<option value="${l.code}">${l.native}</option>`);
  const saved = localStorage.getItem("eystra_lang") || "sv";
  lsel.value = saved;
  await loadLang(saved);
  lsel.addEventListener("change", () => loadLang(lsel.value));

  // Export-språk (samma lista)
  const el = $("exp-lang");
  DEF.langs.forEach(l => el.innerHTML += `<option value="${l.code}">${l.native}</option>`);
  el.value = saved;

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
