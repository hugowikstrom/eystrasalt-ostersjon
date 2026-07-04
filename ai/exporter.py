"""
Export av en simulering till olika dokumentformat:
  * "sida"    — enkel, självständig HTML-sida (öppnas i webbläsare)
  * "pptx"    — PowerPoint-presentation (python-pptx)
  * "rapport" — Word-dokument .docx (python-docx)

Alla format tar samma 'summary'-dict från frontend + valfri rapporttext (kan
AI-genereras på valt språk). En mottagare kan anges (dokumentet adresseras till den).
Returnerar (bytes, filnamn, mimetype).
"""

import html
import io
import json
from datetime import datetime


def _rows_arter(summary):
    return summary.get("arter", []) or []


def _param_items(summary):
    return list((summary.get("parametrar") or {}).items())


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# --- HaV-rapportens fasta avsnittstexter -------------------------------------
# Dispositionen följer Havs- och vattenmyndighetens rapportstruktur. Texterna är
# sakligt korrekta om modellen; den AI-genererade texten (report_text) läggs i
# Sammanfattningen. Nycklar kan översättas via 'strings' (i18n) men har svensk
# fallback här.
SECT = {
    "forord": (
        "Denna rapport är genererad av Eystrasalt — en öppen, pedagogisk digital "
        "tvilling av Östersjöns ekosystem. Rapportens disposition följer Havs- och "
        "vattenmyndighetens rapportstruktur. Eystrasalt är byggt av en enskild "
        "entusiast med stöd av AI och är varken en publikation från eller granskad "
        "av Havs- och vattenmyndigheten. Modellen är en litteraturförankrad "
        "förenkling avsedd för utforskning och lärande — inte en forskningsvaliderad "
        "prognosmodell."),
    "bakgrund": (
        "Östersjön är ett av världens mest övergödda och känsliga innanhav. "
        "Övergödning, klimatuppvärmning, syrefria bottnar och hårt fisketryck "
        "samverkar och har vid flera tillfällen utlöst regimskiften i näringsväven — "
        "mest känt torskens kollaps och storspiggens expansion. Att förstå hur "
        "dessa faktorer hänger ihop kräver att man ser hela kretsloppet, från "
        "näringssalter till toppredatorer."),
    "syfte": (
        "Syftet är att åskådliggöra hur Östersjöns ekosystem svarar på olika "
        "kombinationer av stress (klimat, övergödning, salthalt, fiske och jakt) "
        "och att jämföra förvaltningsstrategier under osäkerhet. Målet är ökad "
        "förståelse och en gemensam, litteraturförankrad utgångspunkt för samtal "
        "om havets framtid."),
    "avgransningar": (
        "Modellen är en förenklad box-modell med 17 kompartment i sex havsområden. "
        "Absoluta värden anges som modellindex i storleksordning g/m² (biomassa), "
        "mg/m³ (näring) och % mättnad (syre) — de är inte kalibrerade "
        "beståndsuppskattningar. Rumslig upplösning, individvariation, detaljerad "
        "hydrografi och ekonomiska data är kraftigt förenklade."),
    "modell": (
        "Ekosystemet beskrivs av kopplade differentialekvationer (en NPZD-modell "
        "utökad med fisk, kustrovfisk, lax, sjöfågel och säl) som löses numeriskt "
        "över vald tidshorisont. Biologiska hastigheter är temperaturberoende "
        "(Q10 = 2). Predation modelleras med mättande funktionellt svar (Holling "
        "typ II). Sex havsområden med salthaltsgradient utbyter näring och salt. "
        "Syret delas i yt- och bottenvatten för att fånga skiktning och syrefria "
        "bottnar. Kväve-sänkor (denitrifikation, utflöde, sedimentbegravning) "
        "sluter näringsbudgeten. Osäkra naturparametrar analyseras med en Monte "
        "Carlo-ensemble."),
    "diskussion": (
        "Resultaten ska tolkas kvalitativt — som riktningar och mekanismer snarare "
        "än exakta prognoser. Modellens styrka är att den visar hur delarna hänger "
        "ihop: hur övergödning och uppvärmning driver syrebrist, hur hårt torskfiske "
        "kan låsa fast ett regimskifte, och hur kustrovfisk och storspigg "
        "konkurrerar. Osäkerheten i naturparametrarna belyses i Monte Carlo-analysen "
        "och känslighetsanalysen (var mer forskning behövs)."),
}

SECT_TITLES = {
    "forord_h": "Förord", "sammanfattning_h": "Sammanfattning",
    "innehall_h": "Innehåll", "inledning_h": "1 Inledning",
    "bakgrund_h": "1.1 Bakgrund", "syfte_h": "1.2 Syfte och mål",
    "avgransningar_h": "1.3 Avgränsningar", "metod_h": "2 Metod",
    "modell_h": "2.1 Modellbeskrivning", "scenario_h": "2.2 Scenario och inställningar",
    "resultat_h": "3 Resultat", "res_halsa_h": "3.1 Ekosystemets hälsa",
    "res_arter_h": "3.2 Arter", "res_pyramid_h": "3.3 Näringspyramid",
    "res_uttak_h": "3.4 Uttag ur havet", "res_strategi_h": "3.5 Strategier och ekonomi",
    "diskussion_h": "4 Diskussion", "slutsatser_h": "5 Slutsatser",
    "referenser_h": "6 Referenser", "bilaga_h": "Bilaga A — Fullständiga inställningar",
}


def _S(strings, key):
    """Avsnittsrubrik: i18n-översättning om den finns, annars svensk fallback."""
    return strings.get(key, SECT_TITLES.get(key, key))


def _slutsatser(summary):
    """Punktvisa slutsatser härledda ur körningens data (ingen påhittad text)."""
    out = []
    hn = summary.get("halsa_nu")
    if hn is not None:
        out.append(f"Ekosystemets hälsoindex i slutet av körningen: {hn} / 100.")
    mc = summary.get("mc")
    if mc and mc.get("basta_namn"):
        out.append(f"Strategin med bäst återhämtning i Monte Carlo-analysen: "
                   f"{mc.get('basta_namn')}.")
    out.append("Resultaten är kvalitativa riktningar från en förenklad modell, "
               "inte prognoser — se Avgränsningar och Diskussion.")
    return out


def _references():
    """Referenslista: modellens litteraturbibliotek + ev. användarens rapporter."""
    refs = []
    try:
        from ai.seed_reports import LIBRARY
        refs.extend(titel for titel, _ in LIBRARY)
    except Exception:
        pass
    try:
        from ai import reports
        for r in reports.list_reports():
            t = r.get("titel", "")
            if t and t not in refs:
                refs.append(t)
    except Exception:
        pass
    return refs


# --- Enkel HTML-sida ---------------------------------------------------------
def _build_html(summary, report_text, recipient, title, strings):
    esc = html.escape
    arter = _rows_arter(summary)
    params = _param_items(summary)
    trofi = summary.get("trofi") or {}
    niv = (trofi.get("nivaer_slut") or {})
    uttak = summary.get("uttak_slut") or {}
    mc = summary.get("mc")

    S = lambda k: _S(strings, k)
    parts = [f"""<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
 body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:820px;margin:0 auto;
   padding:28px;color:#12293f;background:#f5f9fc;line-height:1.5}}
 h1{{color:#0e7490}} h2{{color:#0e7490;border-bottom:2px solid #cde;padding-bottom:4px;margin-top:28px}}
 h3{{color:#155e75;margin-top:18px}}
 table{{border-collapse:collapse;width:100%;margin:8px 0}}
 th,td{{border:1px solid #cde;padding:6px 9px;text-align:right}} th:first-child,td:first-child{{text-align:left}}
 thead th{{background:#e0f2fe}} .muted{{color:#5b7791}} .badge{{background:#e0f2fe;border-radius:8px;padding:2px 8px}}
 .to{{background:#fff;border:1px solid #cde;border-radius:8px;padding:10px 14px;margin:10px 0}}
 .toc{{background:#fff;border:1px solid #cde;border-radius:8px;padding:10px 18px}}
 .toc a{{color:#0e7490;text-decoration:none}} .cover{{text-align:center;padding:24px 0}}
</style></head><body>
<div class="cover">
<h1>🌊 {esc(title)}</h1>
<p class="muted">{esc(strings.get("undertitel","Simulering av Östersjöns ekosystem — digital tvilling"))}</p>
<p class="muted">Rapportstruktur enligt Havs- och vattenmyndighetens mall · Datum: {esc(_today())}</p>
<p class="muted">Utgivare: Eystrasalt — öppen digital tvilling för Östersjön</p>
</div>"""]
    if recipient:
        parts.append(f'<div class="to"><b>{esc(strings.get("till","Till"))}:</b> {esc(recipient)}</div>')

    # Förord
    parts.append(f'<h2 id="forord">{esc(S("forord_h"))}</h2><p>{esc(SECT["forord"])}</p>')

    # Sammanfattning (AI)
    parts.append(f'<h2 id="sammanfattning">{esc(S("sammanfattning_h"))}</h2>')
    if report_text:
        for para in report_text.split("\n"):
            para = para.strip()
            if para:
                parts.append(f"<p>{esc(para)}</p>")
    else:
        parts.append("<p class='muted'>(Ingen sammanfattande text genererades för denna körning.)</p>")

    # Innehåll
    parts.append(f'<h2>{esc(S("innehall_h"))}</h2><div class="toc">'
                 f'<a href="#forord">{esc(S("forord_h"))}</a><br>'
                 f'<a href="#sammanfattning">{esc(S("sammanfattning_h"))}</a><br>'
                 f'<a href="#inledning">{esc(S("inledning_h"))}</a><br>'
                 f'<a href="#metod">{esc(S("metod_h"))}</a><br>'
                 f'<a href="#resultat">{esc(S("resultat_h"))}</a><br>'
                 f'<a href="#diskussion">{esc(S("diskussion_h"))}</a><br>'
                 f'<a href="#slutsatser">{esc(S("slutsatser_h"))}</a><br>'
                 f'<a href="#referenser">{esc(S("referenser_h"))}</a></div>')

    # 1 Inledning
    parts.append(f'<h2 id="inledning">{esc(S("inledning_h"))}</h2>')
    parts.append(f'<h3>{esc(S("bakgrund_h"))}</h3><p>{esc(SECT["bakgrund"])}</p>')
    parts.append(f'<h3>{esc(S("syfte_h"))}</h3><p>{esc(SECT["syfte"])}</p>')
    parts.append(f'<h3>{esc(S("avgransningar_h"))}</h3><p>{esc(SECT["avgransningar"])}</p>')

    # 2 Metod
    parts.append(f'<h2 id="metod">{esc(S("metod_h"))}</h2>')
    parts.append(f'<h3>{esc(S("modell_h"))}</h3><p>{esc(SECT["modell"])}</p>')
    parts.append(f'<h3>{esc(S("scenario_h"))}</h3>')
    if params:
        parts.append('<table><thead><tr><th>Parameter</th><th>Värde</th></tr></thead><tbody>')
        for k, v in params:
            parts.append(f"<tr><td>{esc(str(k))}</td><td>{esc(str(v))}</td></tr>")
        parts.append("</tbody></table>")
    else:
        parts.append("<p class='muted'>Standardinställningar (baslinje).</p>")

    # 3 Resultat
    parts.append(f'<h2 id="resultat">{esc(S("resultat_h"))}</h2>')
    hn = summary.get("halsa_nu")
    if hn is not None:
        parts.append(f'<h3>{esc(S("res_halsa_h"))}</h3>'
                     f'<p><span class="badge">{esc(str(hn))} / 100</span> (index 0–100)</p>')
    if arter:
        parts.append(f'<h3>{esc(S("res_arter_h"))}</h3>'
                     '<table><thead><tr><th>Art</th><th>Start</th><th>Slut</th><th>Enhet</th></tr></thead><tbody>')
        for a in arter:
            parts.append(f"<tr><td>{esc(str(a.get('namn','')))}</td><td>{esc(str(a.get('start','')))}</td>"
                         f"<td>{esc(str(a.get('slut','')))}</td><td class='muted'>{esc(str(a.get('enhet','')))}</td></tr>")
        parts.append("</tbody></table>")
    if niv:
        parts.append(f'<h3>{esc(S("res_pyramid_h"))}</h3><table><thead>'
                     '<tr><th>Nivå</th><th>g/m²</th></tr></thead><tbody>')
        for namn, val in niv.items():
            parts.append(f"<tr><td>{esc(str(namn))}</td><td>{esc(str(val))}</td></tr>")
        parts.append("</tbody></table>")
    if uttak:
        parts.append(f'<h3>{esc(S("res_uttak_h"))}</h3><table><thead>'
                     '<tr><th>Uttag</th><th>g/m²/år</th></tr></thead><tbody>')
        labels = {"fiske": "Fiske (människa)", "sal": "Säl", "skarv": "Skarv/sjöfågel",
                  "atervinning": "Återvinning (nedbrytning→näring)"}
        for k, lab in labels.items():
            if k in uttak:
                parts.append(f"<tr><td>{esc(lab)}</td><td>{esc(str(uttak[k]))}</td></tr>")
        parts.append("</tbody></table>")
    if mc:
        parts.append(f'<h3>{esc(S("res_strategi_h"))}</h3>')
        parts.append(f"<p><b>{esc(str(mc.get('basta_namn','')))}</b></p>")
        eco = mc.get("ekonomi_per_land") or {}
        if eco:
            parts.append("<table><thead><tr><th>Land</th><th>M€/år</th></tr></thead><tbody>")
            for land, v in eco.items():
                parts.append(f"<tr><td>{esc(str(land))}</td><td>{esc(str(v))}</td></tr>")
            parts.append("</tbody></table>")

    # 4 Diskussion
    parts.append(f'<h2 id="diskussion">{esc(S("diskussion_h"))}</h2><p>{esc(SECT["diskussion"])}</p>')

    # 5 Slutsatser
    parts.append(f'<h2 id="slutsatser">{esc(S("slutsatser_h"))}</h2><ul>')
    for s in _slutsatser(summary):
        parts.append(f"<li>{esc(s)}</li>")
    parts.append("</ul>")

    # 6 Referenser
    parts.append(f'<h2 id="referenser">{esc(S("referenser_h"))}</h2><ol>')
    for ref in _references():
        parts.append(f"<li>{esc(ref)}</li>")
    parts.append("</ol>")

    parts.append('<p class="muted" style="margin-top:30px">Genererad av Eystrasalt — '
                 'open source digital tvilling för Östersjön. hugo@bigakwa.com</p>')
    parts.append("</body></html>")
    return "\n".join(parts).encode("utf-8")


# --- PowerPoint --------------------------------------------------------------
def _build_pptx(summary, report_text, recipient, title, strings):
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    blank = prs.slide_layouts[6]
    title_layout = prs.slide_layouts[0]

    # Titelbild
    s = prs.slides.add_slide(title_layout)
    s.shapes.title.text = title
    sub = strings.get("undertitel", "Simulering av Östersjöns ekosystem")
    if recipient:
        sub += f"\n{strings.get('till','Till')}: {recipient}"
    s.placeholders[1].text = sub

    def bullet_slide(rubrik, rader):
        sl = prs.slides.add_slide(blank)
        tb = sl.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(9), Inches(1))
        tf = tb.text_frame; tf.text = rubrik
        tf.paragraphs[0].font.size = Pt(28); tf.paragraphs[0].font.bold = True
        body = sl.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(8.8), Inches(5))
        bf = body.text_frame; bf.word_wrap = True
        for i, r in enumerate(rader):
            p = bf.paragraphs[0] if i == 0 else bf.add_paragraph()
            p.text = "• " + r; p.font.size = Pt(16)

    hn = summary.get("halsa_nu")
    if hn is not None:
        bullet_slide(strings.get("halsa", "Ekosystemets hälsa"),
                     [f"Hälsoindex: {hn} / 100"])
    params = _param_items(summary)
    if params:
        bullet_slide(strings.get("installningar", "Inställningar"),
                     [f"{k}: {v}" for k, v in params])
    arter = _rows_arter(summary)
    if arter:
        bullet_slide(strings.get("arter", "Arter (start → slut)"),
                     [f"{a.get('namn','')}: {a.get('start','')} → {a.get('slut','')} {a.get('enhet','')}"
                      for a in arter])
    niv = (summary.get("trofi") or {}).get("nivaer_slut") or {}
    if niv:
        bullet_slide(strings.get("pyramid", "Näringspyramid"),
                     [f"{namn}: {val}" for namn, val in niv.items()])
    mc = summary.get("mc")
    if mc:
        rows = [f"Bästa strategi: {mc.get('basta_namn','')}"]
        for land, v in (mc.get("ekonomi_per_land") or {}).items():
            rows.append(f"{land}: {v} M€/år")
        bullet_slide(strings.get("strategi", "Strategi & ekonomi"), rows)
    if report_text:
        for chunk_i, chunk in enumerate(_chunks(report_text, 6)):
            bullet_slide(strings.get("sammanfattning", "Sammanfattning")
                         + ("" if chunk_i == 0 else " (forts.)"), chunk)

    buf = io.BytesIO(); prs.save(buf); return buf.getvalue()


def _chunks(text, n):
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    for i in range(0, len(paras), n):
        yield paras[i:i + n]


# --- Word-rapport (struktur enligt Havs- och vattenmyndighetens rapportmall) --
def _toc_field(doc):
    """Infogar ett innehållsförteckningsfält som Word fyller i när dokumentet öppnas."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    p = doc.add_paragraph()
    run = p.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), r'TOC \o "1-2" \h \z \u')
    hint = OxmlElement("w:r"); ht = OxmlElement("w:t")
    ht.text = "Högerklicka och välj „Uppdatera fält” för att bygga innehållsförteckningen."
    hint.append(ht); fld.append(hint)
    run._r.addnext(fld)


def _build_docx(summary, report_text, recipient, title, strings):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    doc = Document()
    S = lambda k: _S(strings, k)

    # --- Titelsida -----------------------------------------------------------
    for _ in range(6):
        doc.add_paragraph()
    h = doc.add_heading(title, 0); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(strings.get("undertitel",
          "Simulering av Östersjöns ekosystem — digital tvilling"))
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = doc.add_paragraph(); meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(f"Rapportstruktur enligt Havs- och vattenmyndighetens mall\n"
                 f"Datum: {_today()}\n"
                 + (f"Mottagare: {recipient}\n" if recipient else "")
                 + "Utgivare: Eystrasalt — öppen digital tvilling för Östersjön")
    doc.add_page_break()

    # --- Förord --------------------------------------------------------------
    doc.add_heading(S("forord_h"), 1)
    doc.add_paragraph(SECT["forord"])

    # --- Sammanfattning (AI-text) -------------------------------------------
    doc.add_heading(S("sammanfattning_h"), 1)
    if report_text:
        for para in report_text.split("\n"):
            para = para.strip()
            if para:
                doc.add_paragraph(para)
    else:
        doc.add_paragraph("(Ingen sammanfattande text genererades för denna körning.)")

    # --- Innehåll ------------------------------------------------------------
    doc.add_heading(S("innehall_h"), 1)
    _toc_field(doc)
    doc.add_page_break()

    # --- 1 Inledning ---------------------------------------------------------
    doc.add_heading(S("inledning_h"), 1)
    doc.add_heading(S("bakgrund_h"), 2); doc.add_paragraph(SECT["bakgrund"])
    doc.add_heading(S("syfte_h"), 2); doc.add_paragraph(SECT["syfte"])
    doc.add_heading(S("avgransningar_h"), 2); doc.add_paragraph(SECT["avgransningar"])

    # --- 2 Metod -------------------------------------------------------------
    doc.add_heading(S("metod_h"), 1)
    doc.add_heading(S("modell_h"), 2); doc.add_paragraph(SECT["modell"])
    doc.add_heading(S("scenario_h"), 2)
    params = _param_items(summary)
    if params:
        t = doc.add_table(rows=1, cols=2); t.style = "Light Grid Accent 1"
        t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Parameter", "Värde"
        for k, v in params:
            c = t.add_row().cells; c[0].text = str(k); c[1].text = str(v)
    else:
        doc.add_paragraph("Standardinställningar (baslinje).")

    # --- 3 Resultat ----------------------------------------------------------
    doc.add_heading(S("resultat_h"), 1)
    hn = summary.get("halsa_nu")
    if hn is not None:
        doc.add_heading(S("res_halsa_h"), 2)
        doc.add_paragraph(f"Hälsoindex (0–100) i slutet av körningen: {hn} / 100.")
    arter = _rows_arter(summary)
    if arter:
        doc.add_heading(S("res_arter_h"), 2)
        t = doc.add_table(rows=1, cols=4); t.style = "Light Grid Accent 1"
        hdr = t.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "Art", "Start", "Slut", "Enhet"
        for a in arter:
            c = t.add_row().cells
            c[0].text = str(a.get("namn", "")); c[1].text = str(a.get("start", ""))
            c[2].text = str(a.get("slut", "")); c[3].text = str(a.get("enhet", ""))
    niv = (summary.get("trofi") or {}).get("nivaer_slut") or {}
    if niv:
        doc.add_heading(S("res_pyramid_h"), 2)
        for namn, val in niv.items():
            doc.add_paragraph(f"{namn}: {val} g/m²", style="List Bullet")
    uttak = summary.get("uttak_slut") or {}
    if uttak:
        doc.add_heading(S("res_uttak_h"), 2)
        labels = {"fiske": "Fiske (människa)", "sal": "Säl", "skarv": "Skarv/sjöfågel",
                  "atervinning": "Återvinning (nedbrytning→näring)"}
        for k, lab in labels.items():
            if k in uttak:
                doc.add_paragraph(f"{lab}: {uttak[k]} g/m²/år", style="List Bullet")
    mc = summary.get("mc")
    if mc:
        doc.add_heading(S("res_strategi_h"), 2)
        doc.add_paragraph(f"Strategi med bäst återhämtning: {mc.get('basta_namn','')}")
        for land, v in (mc.get("ekonomi_per_land") or {}).items():
            doc.add_paragraph(f"{land}: {v} M€/år", style="List Bullet")

    # --- 4 Diskussion --------------------------------------------------------
    doc.add_heading(S("diskussion_h"), 1)
    doc.add_paragraph(SECT["diskussion"])

    # --- 5 Slutsatser --------------------------------------------------------
    doc.add_heading(S("slutsatser_h"), 1)
    for s in _slutsatser(summary):
        doc.add_paragraph(s, style="List Bullet")

    # --- 6 Referenser --------------------------------------------------------
    doc.add_heading(S("referenser_h"), 1)
    for ref in _references():
        doc.add_paragraph(ref, style="List Bullet")

    # --- Bilaga A ------------------------------------------------------------
    if params:
        doc.add_heading(S("bilaga_h"), 1)
        t = doc.add_table(rows=1, cols=2); t.style = "Light Grid Accent 1"
        t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Parameter", "Värde"
        for k, v in params:
            c = t.add_row().cells; c[0].text = str(k); c[1].text = str(v)

    doc.add_paragraph()
    p = doc.add_paragraph("Genererad av Eystrasalt — open source digital tvilling "
                          "för Östersjön. hugo@bigakwa.com")
    p.runs[0].font.size = Pt(9)

    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


# --- Publikt API -------------------------------------------------------------
def export(fmt, summary, report_text=None, recipient="", title="Eystrasalt — Östersjörapport",
           strings=None):
    """Bygger dokumentet. Returnerar (bytes, filnamn, mimetype)."""
    strings = strings or {}
    summary = summary or {}
    if fmt == "sida":
        data = _build_html(summary, report_text, recipient, title, strings)
        return data, "eystrasalt.html", "text/html"
    if fmt == "pptx":
        data = _build_pptx(summary, report_text, recipient, title, strings)
        return data, "eystrasalt.pptx", \
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if fmt == "rapport":
        data = _build_docx(summary, report_text, recipient, title, strings)
        return data, "eystrasalt.docx", \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    raise ValueError(f"Okänt format: {fmt}")
