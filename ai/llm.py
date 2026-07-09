"""
Leverantörsoberoende LLM-klient.

Kärnlogiken i advisor.py bryr sig inte om VILKEN modell som svarar — bara att den
kan skicka en systemprompt + en fråga och få tillbaka text (ev. schematvingad JSON).
Den här modulen kapslar in valet av leverantör så att man kan byta med en miljövariabel.

Två spår, valt via AI_PROVIDER:
  * "anthropic" (default) — Claude via anthropic-SDK:n. Behåller prompt-cachning
    (cache_control) och schematvingad JSON (structured output).
  * "openai"              — valfri OpenAI-kompatibel endpoint: Ollama (lokalt, gratis),
    OpenAI, Groq, Together, Mistral, Gemini m.fl. Anropas med standardbiblioteket
    (urllib) → inget extra pip-beroende behövs för att köra lokalt.

Konfiguration (alla valfria; defaults är bakåtkompatibla):
  AI_PROVIDER   anthropic | openai            (default: anthropic)
  AI_MODEL      modellnamn                    (default: claude-haiku-4-5, resp. llama3.1)
  AI_API_KEY    nyckel                        (anthropic faller tillbaka på ANTHROPIC_API_KEY;
                                               Ollama behöver ingen)
  AI_BASE_URL   endpoint för openai-spåret    (default: http://localhost:11434/v1, Ollama)
  AI_TIMEOUT    sekunder per anrop            (default: 120 — lokala modeller kan vara sega)

Saknas nyckel/endpoint degraderar vi snyggt (available() → False), precis som förr.
"""

import json
import os
import urllib.error
import urllib.request

_DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"   # billigast: $1/$5 per Mtok
_DEFAULT_OLLAMA_MODEL = "llama3.1"
_DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollamas OpenAI-kompatibla endpoint


def provider():
    return os.environ.get("AI_PROVIDER", "anthropic").strip().lower() or "anthropic"


def model():
    m = os.environ.get("AI_MODEL", "").strip()
    if m:
        return m
    return _DEFAULT_OLLAMA_MODEL if provider() == "openai" else _DEFAULT_ANTHROPIC_MODEL


def _api_key():
    # Egen nyckel först; för anthropic-spåret faller vi tillbaka på den gamla variabeln.
    key = os.environ.get("AI_API_KEY", "").strip()
    if key:
        return key
    if provider() == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return ""  # Ollama m.fl. lokala servrar behöver ingen nyckel


def _base_url():
    return os.environ.get("AI_BASE_URL", _DEFAULT_BASE_URL).strip().rstrip("/")


def _timeout():
    try:
        return float(os.environ.get("AI_TIMEOUT", "120"))
    except ValueError:
        return 120.0


_ANTHROPIC_CLIENT = None  # återanvänds mellan anrop


def _anthropic_client():
    global _ANTHROPIC_CLIENT
    if _ANTHROPIC_CLIENT is not None:
        return _ANTHROPIC_CLIENT
    key = _api_key()
    if not key:
        return None
    try:
        import anthropic
        _ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=key)
    except Exception:
        _ANTHROPIC_CLIENT = None
    return _ANTHROPIC_CLIENT


def available():
    """True om vi kan förvänta oss ett svar (nyckel finns / lokal endpoint konfigurerad)."""
    if provider() == "openai":
        # En lokal Ollama behöver ingen nyckel; det räcker att en endpoint är satt.
        return bool(_base_url())
    return _anthropic_client() is not None


def _system_text(system_blocks):
    """Plattar ut advisorns block-lista till en enda systemtext (för openai-spåret)."""
    if isinstance(system_blocks, str):
        return system_blocks
    parts = [b.get("text", "") for b in system_blocks if isinstance(b, dict)]
    return "\n\n".join(p for p in parts if p)


def _complete_anthropic(system_blocks, prompt, max_tokens, schema):
    client = _anthropic_client()
    if client is None:
        raise RuntimeError("anthropic-klient saknas (ingen nyckel)")
    kwargs = dict(
        model=model(),
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": prompt}],
    )
    if schema is not None:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    resp = client.messages.create(**kwargs)
    return next(b.text for b in resp.content if b.type == "text")


def _complete_openai(system_blocks, prompt, max_tokens, schema):
    body = {
        "model": model(),
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": _system_text(system_blocks)},
            {"role": "user", "content": prompt},
        ],
    }
    if schema is not None:
        # Standardformatet för OpenAI-kompatibla servrar. Ollama stöder det i nyare
        # versioner; övriga (OpenAI, Groq, Together …) gör det också.
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": schema, "strict": True},
        }
    headers = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        f"{_base_url()}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_timeout()) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]


def complete(system_blocks, prompt, max_tokens, schema=None):
    """
    Skickar systemprompt + fråga och returnerar modellens text. Kastar vid fel —
    anroparen fångar och faller tillbaka på baslinje (som tidigare).

    system_blocks: advisorns block-lista (anthropic använder den rakt av med
    cache_control; openai-spåret plattar ut den till en systemtext).
    schema: JSON-schema för schematvingad output, eller None för fritext.
    """
    if provider() == "openai":
        return _complete_openai(system_blocks, prompt, max_tokens, schema)
    return _complete_anthropic(system_blocks, prompt, max_tokens, schema)
