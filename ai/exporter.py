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


def _rows_arter(summary):
    return summary.get("arter", []) or []


def _param_items(summary):
    return list((summary.get("parametrar") or {}).items())


# --- Enkel HTML-sida ---------------------------------------------------------
def _build_html(summary, report_text, recipient, title, strings):
    esc = html.escape
    arter = _rows_arter(summary)
    params = _param_items(summary)
    trofi = summary.get("trofi") or {}
    niv = (trofi.get("nivaer_slut") or {})
    uttak = summary.get("uttak_slut") or {}
    mc = summary.get("mc")

    parts = [f"""<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
 body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:820px;margin:0 auto;
   padding:28px;color:#12293f;background:#f5f9fc;line-height:1.5}}
 h1{{color:#0e7490}} h2{{color:#0e7490;border-bottom:2px solid #cde;padding-bottom:4px;margin-top:28px}}
 table{{border-collapse:collapse;width:100%;margin:8px 0}}
 th,td{{border:1px solid #cde;padding:6px 9px;text-align:right}} th:first-child,td:first-child{{text-align:left}}
 thead th{{background:#e0f2fe}} .muted{{color:#5b7791}} .badge{{background:#e0f2fe;border-radius:8px;padding:2px 8px}}
 .to{{background:#fff;border:1px solid #cde;border-radius:8px;padding:10px 14px;margin:10px 0}}
</style></head><body>
<h1>🌊 {esc(title)}</h1>"""]
    if recipient:
        parts.append(f'<div class="to"><b>{esc(strings.get("till","Till"))}:</b> {esc(recipient)}</div>')
    parts.append(f'<p class="muted">{esc(strings.get("undertitel","Simulering av Östersjöns ekosystem — digital tvilling"))}</p>')

    if report_text:
        # report_text är ren text/markdown-ish → visa styckevis
        parts.append(f'<h2>{esc(strings.get("sammanfattning","Sammanfattning"))}</h2>')
        for para in report_text.split("\n"):
            para = para.strip()
            if para:
                parts.append(f"<p>{esc(para)}</p>")

    if params:
        parts.append(f'<h2>{esc(strings.get("installningar","Inställningar"))}</h2><table><tbody>')
        for k, v in params:
            parts.append(f"<tr><td>{esc(str(k))}</td><td>{esc(str(v))}</td></tr>")
        parts.append("</tbody></table>")

    hn = summary.get("halsa_nu")
    if hn is not None:
        parts.append(f'<h2>{esc(strings.get("halsa","Ekosystemets hälsa"))}</h2>'
                     f'<p><span class="badge">{esc(str(hn))} / 100</span></p>')

    if arter:
        parts.append(f'<h2>{esc(strings.get("arter","Arter (start → slut)"))}</h2>'
                     '<table><thead><tr><th>Art</th><th>Start</th><th>Slut</th><th>Enhet</th></tr></thead><tbody>')
        for a in arter:
            parts.append(f"<tr><td>{esc(str(a.get('namn','')))}</td><td>{esc(str(a.get('start','')))}</td>"
                         f"<td>{esc(str(a.get('slut','')))}</td><td class='muted'>{esc(str(a.get('enhet','')))}</td></tr>")
        parts.append("</tbody></table>")

    if niv:
        parts.append(f'<h2>{esc(strings.get("pyramid","Näringspyramid (biomassa per nivå)"))}</h2><table><tbody>')
        for namn, val in niv.items():
            parts.append(f"<tr><td>{esc(str(namn))}</td><td>{esc(str(val))}</td></tr>")
        parts.append("</tbody></table>")

    if uttak:
        parts.append(f'<h2>{esc(strings.get("uttak","Uttag ur havet (per år)"))}</h2><table><tbody>')
        labels = {"fiske": "Fiske (människa)", "sal": "Säl", "skarv": "Skarv/sjöfågel",
                  "atervinning": "Återvinning (nedbrytning→näring)"}
        for k, lab in labels.items():
            if k in uttak:
                parts.append(f"<tr><td>{esc(lab)}</td><td>{esc(str(uttak[k]))}</td></tr>")
        parts.append("</tbody></table>")

    if mc:
        parts.append(f'<h2>{esc(strings.get("strategi","Bästa strategi & ekonomi"))}</h2>')
        parts.append(f"<p><b>{esc(str(mc.get('basta_namn','')))}</b></p>")
        eco = mc.get("ekonomi_per_land") or {}
        if eco:
            parts.append("<table><thead><tr><th>Land</th><th>M€/år</th></tr></thead><tbody>")
            for land, v in eco.items():
                parts.append(f"<tr><td>{esc(str(land))}</td><td>{esc(str(v))}</td></tr>")
            parts.append("</tbody></table>")

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


# --- Word-rapport ------------------------------------------------------------
def _build_docx(summary, report_text, recipient, title, strings):
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.add_heading(title, 0)
    if recipient:
        doc.add_paragraph(f"{strings.get('till','Till')}: {recipient}")
    doc.add_paragraph(strings.get("undertitel", "Simulering av Östersjöns ekosystem — digital tvilling"))

    if report_text:
        doc.add_heading(strings.get("sammanfattning", "Sammanfattning"), 1)
        for para in report_text.split("\n"):
            para = para.strip()
            if para:
                doc.add_paragraph(para)

    params = _param_items(summary)
    if params:
        doc.add_heading(strings.get("installningar", "Inställningar"), 1)
        for k, v in params:
            doc.add_paragraph(f"{k}: {v}", style="List Bullet")

    hn = summary.get("halsa_nu")
    if hn is not None:
        doc.add_heading(strings.get("halsa", "Ekosystemets hälsa"), 1)
        doc.add_paragraph(f"Hälsoindex: {hn} / 100")

    arter = _rows_arter(summary)
    if arter:
        doc.add_heading(strings.get("arter", "Arter (start → slut)"), 1)
        t = doc.add_table(rows=1, cols=4); t.style = "Light Grid Accent 1"
        hdr = t.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "Art", "Start", "Slut", "Enhet"
        for a in arter:
            c = t.add_row().cells
            c[0].text = str(a.get("namn", "")); c[1].text = str(a.get("start", ""))
            c[2].text = str(a.get("slut", "")); c[3].text = str(a.get("enhet", ""))

    niv = (summary.get("trofi") or {}).get("nivaer_slut") or {}
    if niv:
        doc.add_heading(strings.get("pyramid", "Näringspyramid"), 1)
        for namn, val in niv.items():
            doc.add_paragraph(f"{namn}: {val}", style="List Bullet")

    mc = summary.get("mc")
    if mc:
        doc.add_heading(strings.get("strategi", "Bästa strategi & ekonomi"), 1)
        doc.add_paragraph(f"Bästa strategi: {mc.get('basta_namn','')}")
        for land, v in (mc.get("ekonomi_per_land") or {}).items():
            doc.add_paragraph(f"{land}: {v} M€/år", style="List Bullet")

    doc.add_paragraph()
    p = doc.add_paragraph("Genererad av Eystrasalt — open source digital tvilling för Östersjön. hugo@bigakwa.com")
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
