"""
Delad lagringshjälp för fil-baserade JSON-poster (rapporter, sparade körningar, idéer).

Härdad mot de problem säkerhetsgranskningen pekade ut (F-07):
  * ID-tilldelning är kapplöpningssäker även mellan processer (gunicorn-arbetare):
    vi *reserverar* id-filen med O_CREAT|O_EXCL innan vi skriver, och backar om
    någon annan hann före.
  * Skrivningar är atomära (skriv till temp-fil + os.replace) så en krasch mitt i
    en skrivning aldrig lämnar en trasig JSON-fil.
  * En process-lokal lås serialiserar skrivningar inom processen.

Ingen databas behövs — en fil per post, id = löpnummer.
"""

import glob
import json
import os
import re
import threading

_LOCK = threading.Lock()
_NAME_RE = re.compile(r"(\d+)\.json$")


def ensure(directory):
    os.makedirs(directory, exist_ok=True)


def path(directory, item_id):
    return os.path.join(directory, f"{int(item_id)}.json")


def _existing_ids(directory):
    ids = []
    for p in glob.glob(os.path.join(directory, "*.json")):
        m = _NAME_RE.search(os.path.basename(p))
        if m:
            ids.append(int(m.group(1)))
    return ids


def write_atomic(target, obj):
    """Skriv JSON atomärt: temp-fil + fsync + os.replace."""
    tmp = f"{target}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def create(directory, build_obj):
    """
    Reservera nästa lediga id, bygg posten med build_obj(id) och skriv den atomärt.

    build_obj(item_id) -> dict. Returnerar den sparade posten.
    Kapplöpningssäker: om två skrivare tävlar om samma id backar den ena och tar nästa.
    """
    ensure(directory)
    with _LOCK:
        while True:
            ids = _existing_ids(directory)
            nid = (max(ids) + 1) if ids else 1
            target = path(directory, nid)
            try:
                # Reservera id-filen exklusivt (även mellan processer).
                fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.close(fd)
            except FileExistsError:
                continue  # någon annan hann före — ta nästa id
            obj = build_obj(nid)
            write_atomic(target, obj)
            return obj


def load_all(directory):
    """Alla poster (hoppar tyst över trasiga/halvskrivna filer)."""
    ensure(directory)
    out = []
    for p in sorted(glob.glob(os.path.join(directory, "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def delete(directory, item_id):
    p = path(directory, item_id)
    if os.path.exists(p):
        os.remove(p)
        return True
    return False
