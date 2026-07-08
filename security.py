"""
Säkerhetslager för Flask-appen — samlar åtgärderna från säkerhetsgranskningen
(eystrasalt_security_report) på ett ställe:

  F-02  Skydda destruktiva/publikations-endpoints med lösenord (kräver "abborre").
  F-03  Storleksgräns på request-body + enkel takt-begränsning (rate limit) per IP.
  F-05  CORS av som standard; slås bara på för uttryckliga origins (ALLOWED_ORIGINS).
  F-06  Content-Security-Policy och övriga säkerhetsheaders på varje svar.
  F-10  Debug är AV som standard; slås bara på i utvecklingsläge.

Konfiguration via miljövariabler (läses live så att __main__ kan sätta standard):
  APP_ENV          "development" | "production"  (standard: production)
  ADMIN_PASSWORD   lösenord för att lägga till/ta bort publikationer (standard: abborre)
  ALLOWED_ORIGINS  kommaseparerad lista av tillåtna origins för /api/* (standard: inga)
  MAX_CONTENT_KB   maximal request-storlek i KiB (standard: 512)
"""

import hmac
import os
import threading
import time
from functools import wraps

from flask import abort, jsonify, request


# --- Konfiguration (läses live ur miljön) ------------------------------------
def app_env():
    return os.environ.get("APP_ENV", "production").strip().lower()


def is_dev():
    return app_env() == "development"


def admin_password():
    # Standard "abborre" så publikationshanteringen är lösenordsskyddad direkt.
    return os.environ.get("ADMIN_PASSWORD", "abborre")


def max_content_length():
    try:
        return int(os.environ.get("MAX_CONTENT_KB", "512")) * 1024
    except ValueError:
        return 512 * 1024


def allowed_origins():
    return [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]


# --- Lösenordsskydd för publikationer/moderering (F-02) ----------------------
def _provided_password():
    return (request.headers.get("X-Admin-Password")
            or (request.get_json(silent=True) or {}).get("password")
            or request.args.get("password")
            or "")


def check_password():
    """Är rätt lösenord angivet? (konstant-tids-jämförelse)."""
    want = admin_password()
    return bool(want) and hmac.compare_digest(str(_provided_password()), str(want))


def require_admin(f):
    """Kräver rätt lösenord (abborre) för destruktiva/publikations-endpoints."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not check_password():
            return jsonify({"error": "Fel lösenord. Ange lösenordet för att hantera publikationer."}), 403
        return f(*args, **kwargs)
    return wrapper


# --- Takt-begränsning per IP (F-03) ------------------------------------------
# Enkel fönster-räknare i minnet. Per process (per gunicorn-arbetare) — komplettera
# gärna med gränser i den omvända proxyn (Caddy/nginx) för en instans med flera arbetare.
_BUCKETS = {}
_RL_LOCK = threading.Lock()


def _client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "?"


def rate_limit(max_calls, per_seconds):
    """Dekorator: högst max_calls anrop per per_seconds och IP för denna route."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            now = time.time()
            key = (f.__name__, _client_ip())
            with _RL_LOCK:
                start, count = _BUCKETS.get(key, (now, 0))
                if now - start >= per_seconds:
                    start, count = now, 0
                count += 1
                _BUCKETS[key] = (start, count)
                over = count > max_calls
                retry = int(per_seconds - (now - start)) + 1
            if over:
                resp = jsonify({"error": "För många förfrågningar. Försök igen om en stund."})
                resp.status_code = 429
                resp.headers["Retry-After"] = str(max(retry, 1))
                return resp
            return f(*args, **kwargs)
        return wrapper
    return deco


# --- Säkerhetsheaders + CSP (F-06) -------------------------------------------
# Appen laddar bara egna resurser (style.css, app.js) men bygger inline-SVG och
# sätter inline style-attribut → style-src behöver 'unsafe-inline'. Inga inline-
# script eller externa CDN:er, så script-src kan hållas strikt till 'self'.
CSP = ("default-src 'self'; "
       "script-src 'self'; "
       "style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; "
       "connect-src 'self'; "
       "object-src 'none'; "
       "base-uri 'self'; "
       "frame-ancestors 'none'; "
       "form-action 'self'")


def _security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=(self)")
    return resp


def init_security(app):
    """Kopplar in säkerhetsåtgärderna på Flask-appen. Anropas en gång vid start."""
    # F-03: storleksgräns på inkommande body.
    app.config["MAX_CONTENT_LENGTH"] = max_content_length()

    # F-05: CORS av som standard; endast uttryckliga origins för /api/*.
    origins = allowed_origins()
    if origins:
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=False)

    # F-06: säkerhetsheaders på varje svar.
    app.after_request(_security_headers)

    @app.errorhandler(413)
    def _too_large(_e):
        return jsonify({"error": "Förfrågan är för stor."}), 413

    return app
