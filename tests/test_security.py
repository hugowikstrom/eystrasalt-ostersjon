"""
Regressionstester för säkerhetsgränserna (åtgärderna från säkerhetsgranskningen).

Kör:  python -m pytest tests/ -q
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Isolera all fil-lagring till en temp-katalog så testerna inte rör riktig data.
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "abborre")
    monkeypatch.setenv("ALLOWED_ORIGINS", "")

    import ai.ideas as ideas
    import ai.reports as reports
    import ai.saved as saved
    monkeypatch.setattr(ideas, "IDEAS_DIR", str(tmp_path / "ideas"))
    monkeypatch.setattr(reports, "REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(saved, "SAVED_DIR", str(tmp_path / "saved"))

    import app as app_module
    importlib.reload(app_module)
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


# --- F-01: lagrad XSS-payload lagras men neutraliseras vid rendering ----------
def test_idea_xss_payload_stored_verbatim(client):
    payload = '<img src=x onerror=alert(1)>'
    r = client.post("/api/ideas", json={"namn": "<b>hej</b>", "text": payload})
    assert r.status_code == 200
    got = client.get("/api/ideas").get_json()["ideer"][0]
    # Backend lagrar råtext; escaping sker i frontend (escHtml). Ingen dubbel-escaping här.
    assert got["text"] == payload


def test_escape_helper_in_frontend_source():
    js = open(os.path.join(os.path.dirname(__file__), "..", "web", "app.js"), encoding="utf-8").read()
    assert "function escHtml" in js
    # Idé- och publikationsrendering ska gå via escHtml.
    assert "escHtml(i.text)" in js
    assert "escHtml(r.titel)" in js


# --- F-02: publikationer/moderering kräver lösenord ---------------------------
def test_add_report_requires_password(client):
    r = client.post("/api/reports", json={"titel": "T", "text": "hej"})
    assert r.status_code == 403


def test_add_report_with_password(client):
    r = client.post("/api/reports", json={"titel": "T", "text": "hej"},
                    headers={"X-Admin-Password": "abborre"})
    assert r.status_code == 200 and r.get_json()["ok"]


def test_delete_report_requires_password(client):
    client.post("/api/reports", json={"titel": "T", "text": "hej"},
                headers={"X-Admin-Password": "abborre"})
    assert client.delete("/api/reports/1").status_code == 403
    ok = client.delete("/api/reports/1", headers={"X-Admin-Password": "abborre"})
    assert ok.status_code == 200


def test_delete_idea_requires_password(client):
    client.post("/api/ideas", json={"text": "en idé"})
    assert client.delete("/api/ideas/1").status_code == 403
    assert client.delete("/api/ideas/1", headers={"X-Admin-Password": "abborre"}).status_code == 200


def test_wrong_password_rejected(client):
    r = client.post("/api/reports", json={"titel": "T", "text": "x"},
                    headers={"X-Admin-Password": "torsk"})
    assert r.status_code == 403


# --- F-03: storleksgräns + takt-begränsning -----------------------------------
def test_max_content_length_set(client):
    assert client.application.config["MAX_CONTENT_LENGTH"] == 512 * 1024


def test_oversized_body_rejected(client):
    big = "a" * (600 * 1024)
    r = client.post("/api/ideas", data=big, content_type="application/json")
    assert r.status_code == 413


def test_rate_limit_montecarlo(client):
    # 6/min → sjunde anropet ska ge 429.
    codes = [client.post("/api/montecarlo", json={"draws": 1}).status_code for _ in range(8)]
    assert 429 in codes


# --- F-05 / F-06: CORS av som standard, säkerhetsheaders på plats --------------
def test_no_cors_by_default(client):
    r = client.get("/api/defaults", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_security_headers_present(client):
    r = client.get("/api/defaults")
    assert "Content-Security-Policy" in r.headers
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


# --- F-07: atomär, kapplöpningssäker lagring ----------------------------------
def test_storage_unique_ids(client):
    import ai.ideas as ideas
    ids = {ideas.add_idea("x", f"idé {i}")["id"] for i in range(25)}
    assert len(ids) == 25  # inga dubbletter


def test_empty_idea_rejected(client):
    r = client.post("/api/ideas", json={"text": "   "})
    assert r.status_code == 400
