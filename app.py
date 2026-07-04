"""
Flask-backend för Östersjö-simuleringen (Eystrasalt).

Serverar webbappen (web/) och ett API:
  GET  /api/defaults        — zoner, arter, enheter, scenarier, hjälptexter, baslinje
  POST /api/simulate        — kör simuleringen → tidsserier
  POST /api/montecarlo      — jämför strategier under osäkerhet (10/20/50/100 år)
  GET  /api/verify          — verifiera modellen mot litteraturen
  GET/POST/DELETE /api/reports — hantera inlagda rapporter (AI-underlag)
  POST /api/ai/scenario     — fri text → parametrar (Claude)
  POST /api/ai/explain      — förklara ett resultat (Claude)
  POST /api/ai/research     — var mer forskning behövs (Claude)

Kör:  python app.py   (serverar på http://localhost:5800)
"""

import os
# Håll varje process till 1 BLAS-tråd (Monte Carlo parallelliserar över processer).
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import io
import json

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

load_dotenv()  # läser ANTHROPIC_API_KEY från .env

from ai import advisor, reports, saved, ideas, exporter, i18n
from model import scenarios, montecarlo, verification
from model import species as S
from model.ecosystem import EcoParams, simulate
from model.zones import ZONES

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
CORS(app)


_TODAY_HEALTH = None  # cache: dagens (baslinjens) hälsa räknas en gång per serverstart


def _today_health():
    """Ekosystemets hälsa idag (baslinjen, inga åtgärder). Cachas."""
    global _TODAY_HEALTH
    if _TODAY_HEALTH is None:
        from model import health as H
        res = simulate(EcoParams(years=5))
        _TODAY_HEALTH = H.health_at(res, 1)
    return _TODAY_HEALTH


def _load_help():
    try:
        with open(os.path.join(DATA_DIR, "help.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _params_from_json(data):
    """Bygger EcoParams från inkommande JSON (med säkra standardvärden)."""
    p = EcoParams()
    p.years = float(data.get("years", 30))
    p.temp_delta = float(data.get("temp_delta", 0.0))
    p.nutrient_load = float(data.get("nutrient_load", 1.0))
    p.salinity_delta = float(data.get("salinity_delta", 0.0))
    p.seal_hunt = float(data.get("seal_hunt", 0.0))
    p.bird_hunt = float(data.get("bird_hunt", 0.0))
    p.noise = float(data.get("noise", 0.0))
    p.noise_seed = int(data.get("noise_seed", 0))
    fishing = data.get("fishing") or {}
    for art in ("sill", "skarpsill", "spigg", "abborre", "gadda", "torsk", "lax"):
        if art in fishing:
            p.fishing[art] = float(fishing[art])
    # klämm värden till rimliga intervall
    p.years = min(max(p.years, 5), 100)
    p.temp_delta = min(max(p.temp_delta, -2), 8)
    p.nutrient_load = min(max(p.nutrient_load, 0.0), 4)
    p.salinity_delta = min(max(p.salinity_delta, -5), 5)
    p.seal_hunt = min(max(p.seal_hunt, 0.0), 5)
    p.bird_hunt = min(max(p.bird_hunt, 0.0), 5)
    p.noise = min(max(p.noise, 0.0), 3)
    return p


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/api/defaults")
def defaults():
    base = EcoParams()
    return jsonify({
        "zones": [{"key": z.key, "name": z.name, "salinity": z.salinity,
                   "temp_mean": z.temp_mean, "depth": z.depth,
                   "has_deep_basin": z.has_deep_basin, "x": z.x, "y": z.y}
                  for z in ZONES],
        "scenarios": scenarios.list_scenarios(),
        "compartments": S.COMPARTMENTS,
        "display": S.DISPLAY,
        "units": S.UNIT,
        "diet": S.DIET,
        "help": _load_help(),
        "langs": i18n.LANGS,
        "dagens_halsa": _today_health(),
        "baseline": {
            "years": base.years, "temp_delta": base.temp_delta,
            "nutrient_load": base.nutrient_load, "salinity_delta": base.salinity_delta,
            "seal_hunt": base.seal_hunt, "bird_hunt": base.bird_hunt, "noise": base.noise,
            "fishing": base.fishing,
        },
    })


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    data = request.get_json(force=True) or {}
    key = data.get("scenario")
    if key:
        p = scenarios.get_scenario(key, years=float(data.get("years", 30)))
    else:
        p = _params_from_json(data)
    return jsonify(simulate(p))


@app.route("/api/montecarlo", methods=["POST"])
def api_montecarlo():
    data = request.get_json(force=True) or {}
    out = montecarlo.run(
        draws=int(data.get("draws", 16)),
        temp_delta=float(data.get("temp_delta", 0.0)),
        salinity_delta=float(data.get("salinity_delta", 0.0)),
        nutrient_load=float(data.get("nutrient_load", 1.0)),
    )
    return jsonify(out)


@app.route("/api/verify")
def api_verify():
    return jsonify(verification.run())


@app.route("/api/reports", methods=["GET", "POST"])
def api_reports():
    if request.method == "GET":
        return jsonify({"rapporter": reports.list_reports()})
    data = request.get_json(force=True) or {}
    try:
        meta = reports.add_report(data.get("titel"), data.get("text"))
        return jsonify({"ok": True, "rapport": meta})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/reports/<int:rid>", methods=["DELETE"])
def api_reports_delete(rid):
    return jsonify({"ok": reports.delete_report(rid)})


@app.route("/api/ai/scenario", methods=["POST"])
def api_ai_scenario():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Ingen text angavs."}), 400
    return jsonify(advisor.parse_scenario(text, current=data.get("current")))


@app.route("/api/ai/explain", methods=["POST"])
def api_ai_explain():
    data = request.get_json(force=True) or {}
    summary = data.get("summary")
    if not summary:
        return jsonify({"error": "Ingen sammanfattning angavs."}), 400
    return jsonify({"text": advisor.explain_result(summary)})


@app.route("/api/ai/research", methods=["POST"])
def api_ai_research():
    data = request.get_json(force=True) or {}
    sens = data.get("kanslighet")
    if not sens:
        return jsonify({"error": "Kör Monte Carlo först (saknar känslighetsdata)."}), 400
    return jsonify({"text": advisor.suggest_research(sens, best=data.get("basta"))})


@app.route("/api/ai/suggest-reports", methods=["POST"])
def api_ai_suggest_reports():
    data = request.get_json(force=True) or {}
    return jsonify({"text": advisor.suggest_reports(data.get("kanslighet"))})


# --- Spara/ladda parameteruppsättningar (server) -----------------------------
@app.route("/api/saved", methods=["GET", "POST"])
def api_saved():
    if request.method == "GET":
        return jsonify({"sparade": saved.list_saved(request.args.get("user"))})
    data = request.get_json(force=True) or {}
    meta = saved.save(data.get("namn"), data.get("params"),
                      data.get("summary"), data.get("user"))
    return jsonify({"ok": True, "sparad": meta})


@app.route("/api/saved/<int:sid>", methods=["DELETE"])
def api_saved_delete(sid):
    return jsonify({"ok": saved.delete(sid)})


# --- Idélåda -----------------------------------------------------------------
@app.route("/api/ideas", methods=["GET", "POST"])
def api_ideas():
    if request.method == "GET":
        return jsonify({"ideer": ideas.list_ideas()})
    data = request.get_json(force=True) or {}
    try:
        return jsonify({"ok": True, "ide": ideas.add_idea(data.get("namn"), data.get("text"))})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/ideas/<int:iid>", methods=["DELETE"])
def api_ideas_delete(iid):
    return jsonify({"ok": ideas.delete(iid)})


# --- Flerspråkighet ----------------------------------------------------------
@app.route("/api/i18n/<code>")
def api_i18n(code):
    return jsonify(i18n.get(code))


# --- Export (enkel sida / PowerPoint / rapport) ------------------------------
@app.route("/api/export", methods=["POST"])
def api_export():
    data = request.get_json(force=True) or {}
    fmt = data.get("format", "sida")
    lang = data.get("lang", "sv")
    strings = i18n.get(lang)
    summary = data.get("summary") or {}
    title = data.get("title") or "Eystrasalt — Östersjörapport"
    recipient = (data.get("recipient") or "").strip()
    report_text = None
    if data.get("ai_text"):
        report_text = advisor.report_text(summary, i18n.LANG_NAME.get(lang, "svenska"))
    try:
        blob, filename, mime = exporter.export(
            fmt, summary, report_text=report_text, recipient=recipient,
            title=title, strings=strings)
    except Exception as e:
        return jsonify({"error": f"Exportfel: {type(e).__name__}: {e}"}), 400
    return send_file(io.BytesIO(blob), mimetype=mime,
                     as_attachment=True, download_name=filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5800))
    app.run(host="0.0.0.0", port=port, debug=True)
