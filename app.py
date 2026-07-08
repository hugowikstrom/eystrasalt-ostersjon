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

load_dotenv()  # läser ANTHROPIC_API_KEY från .env

import security
from ai import advisor, reports, saved, ideas, exporter, i18n
from model import scenarios, montecarlo, verification, foodweb
from model import species as S
from model.ecosystem import EcoParams, simulate
from model.zones import ZONES

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
security.init_security(app)   # CORS-policy, säkerhetsheaders, storleksgräns (se security.py)


# --- Monte Carlo-cache -------------------------------------------------------
# MC är den tyngsta körningen men helt deterministisk (fast frö). Vi sparar
# resultatet på disk per unik uppsättning indata, så identiska körningar hämtas
# direkt istället för att räknas om. Modellversionen (hash av model/*.py) ingår
# i nyckeln → cachen ogiltigförklaras automatiskt om modellen ändras.
import glob
import hashlib

MC_CACHE_DIR = os.path.join(DATA_DIR, "mc_cache")


def _model_version():
    h = hashlib.sha1()
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "model", "*.py"))):
        with open(f, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:10]


_MODEL_VER = _model_version()


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
    p.noise = float(data.get("noise", 0.7))
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
        "ekologi": foodweb.matrix(),
        "dagens_halsa": _today_health(),
        "baseline": {
            "years": base.years, "temp_delta": base.temp_delta,
            "nutrient_load": base.nutrient_load, "salinity_delta": base.salinity_delta,
            "seal_hunt": base.seal_hunt, "bird_hunt": base.bird_hunt, "noise": base.noise,
            "fishing": base.fishing,
        },
    })


@app.route("/api/simulate", methods=["POST"])
@security.rate_limit(60, 60)
def api_simulate():
    data = request.get_json(silent=True) or {}
    key = data.get("scenario")
    if key:
        p = scenarios.get_scenario(key, years=float(data.get("years", 30)))
    else:
        p = _params_from_json(data)
    return jsonify(simulate(p))


@app.route("/api/montecarlo", methods=["POST"])
@security.rate_limit(6, 60)
def api_montecarlo():
    data = request.get_json(silent=True) or {}
    draws = int(data.get("draws", 16))
    td = float(data.get("temp_delta", 0.0))
    sd = float(data.get("salinity_delta", 0.0))
    nl = float(data.get("nutrient_load", 1.0))

    # Cache-nyckel: modellversion + alla indata (MC är deterministisk)
    key = f"{_MODEL_VER}|{draws}|{td:.4f}|{sd:.4f}|{nl:.4f}"
    fname = hashlib.sha1(key.encode()).hexdigest()[:16] + ".json"
    path = os.path.join(MC_CACHE_DIR, fname)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            out = json.load(f)
        out["cachad"] = True          # frontend kan visa att det kom från cache
        return jsonify(out)

    out = montecarlo.run(draws=draws, temp_delta=td, salinity_delta=sd, nutrient_load=nl)
    try:
        os.makedirs(MC_CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
    except Exception:
        pass                          # cache är en bonus; strunta i skrivfel
    out["cachad"] = False
    return jsonify(out)


@app.route("/api/verify")
def api_verify():
    return jsonify(verification.run())


@app.route("/api/reports", methods=["GET", "POST"])
def api_reports():
    if request.method == "GET":
        return jsonify({"rapporter": reports.list_reports()})
    # F-02: att lägga till publikationer kräver lösenord (abborre).
    if not security.check_password():
        return jsonify({"error": "Fel lösenord. Ange lösenordet för att hantera publikationer."}), 403
    data = request.get_json(silent=True) or {}
    try:
        meta = reports.add_report(data.get("titel"), data.get("text"))
        return jsonify({"ok": True, "rapport": meta})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/reports/<int:rid>", methods=["DELETE"])
@security.require_admin
def api_reports_delete(rid):
    return jsonify({"ok": reports.delete_report(rid)})


@app.route("/api/ai/scenario", methods=["POST"])
@security.rate_limit(10, 60)
def api_ai_scenario():
    data = request.get_json(silent=True) or {}
    text = (str(data.get("text") or "")).strip()[:4000]
    if not text:
        return jsonify({"error": "Ingen text angavs."}), 400
    return jsonify(advisor.parse_scenario(text, current=data.get("current")))


@app.route("/api/ai/explain", methods=["POST"])
@security.rate_limit(10, 60)
def api_ai_explain():
    data = request.get_json(silent=True) or {}
    summary = data.get("summary")
    if not summary:
        return jsonify({"error": "Ingen sammanfattning angavs."}), 400
    return jsonify({"text": advisor.explain_result(summary)})


@app.route("/api/ai/research", methods=["POST"])
@security.rate_limit(10, 60)
def api_ai_research():
    data = request.get_json(silent=True) or {}
    sens = data.get("kanslighet")
    if not sens:
        return jsonify({"error": "Kör Monte Carlo först (saknar känslighetsdata)."}), 400
    return jsonify({"text": advisor.suggest_research(sens, best=data.get("basta"))})


@app.route("/api/ai/suggest-reports", methods=["POST"])
@security.rate_limit(10, 60)
def api_ai_suggest_reports():
    data = request.get_json(silent=True) or {}
    return jsonify({"text": advisor.suggest_reports(data.get("kanslighet"))})


# --- Spara/ladda parameteruppsättningar (server) -----------------------------
@app.route("/api/saved", methods=["GET", "POST"])
@security.rate_limit(40, 60)
def api_saved():
    if request.method == "GET":
        return jsonify({"sparade": saved.list_saved(request.args.get("user"))})
    data = request.get_json(silent=True) or {}
    meta = saved.save(data.get("namn"), data.get("params"),
                      data.get("summary"), data.get("user"))
    return jsonify({"ok": True, "sparad": meta})


@app.route("/api/saved/<int:sid>", methods=["DELETE"])
@security.rate_limit(40, 60)
def api_saved_delete(sid):
    return jsonify({"ok": saved.delete(sid)})


# --- Idélåda -----------------------------------------------------------------
@app.route("/api/ideas", methods=["GET", "POST"])
@security.rate_limit(20, 60)
def api_ideas():
    if request.method == "GET":
        return jsonify({"ideer": ideas.list_ideas()})
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, "ide": ideas.add_idea(data.get("namn"), data.get("text"))})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/ideas/<int:iid>", methods=["DELETE"])
@security.require_admin
def api_ideas_delete(iid):
    return jsonify({"ok": ideas.delete(iid)})


# --- Flerspråkighet ----------------------------------------------------------
@app.route("/api/i18n/<code>")
def api_i18n(code):
    return jsonify(i18n.get(code))


# --- Export (enkel sida / PowerPoint / rapport) ------------------------------
@app.route("/api/export", methods=["POST"])
@security.rate_limit(20, 60)
def api_export():
    data = request.get_json(silent=True) or {}
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
    # Direkt "python app.py" är utvecklings-entrypointen → utvecklingsläge om inget
    # annat sagts. Publik drift körs via gunicorn (se README) där APP_ENV=production.
    os.environ.setdefault("APP_ENV", "development")
    port = int(os.environ.get("PORT", 5800))
    # F-10: debug är AV som standard; slås bara på med FLASK_DEBUG=1.
    debug = os.environ.get("FLASK_DEBUG", "").strip() in ("1", "true", "True")
    # Bind till localhost i debugläge (Werkzeug-debuggern får aldrig exponeras publikt).
    host = "127.0.0.1" if debug else "0.0.0.0"
    app.run(host=host, port=port, debug=debug)
