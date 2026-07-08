#!/usr/bin/env bash
#
# deploy.sh — säker, idempotent deploy/uppdatering av Eystrasalt.
#
# Gör följande, och kan köras om hur många gånger som helst:
#   1. Uppdaterar koden (git fetch + ff-only pull på vald branch)
#   2. Skapar/uppdaterar virtuell miljö och installerar fastnaglade beroenden
#   3. Smoke-test: importerar appen
#   4. Seedar forskningsbiblioteket
#   5. Lägger hemligheter (ADMIN_PASSWORD m.m.) i en root-skyddad env-fil — ALDRIG i git
#   6. Installerar/uppdaterar en härdad systemd-tjänst och startar om den
#   7. Hälsokoll mot API:t
#
# Användning:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Överrid via miljövariabler vid behov:
#   BRANCH=main BIND=127.0.0.1:5800 WORKERS=4 SERVICE=eystrasalt ./deploy.sh
#   REPO_DIR=/home/huggo/balticsea ./deploy.sh      # om scriptet ligger på annat ställe
#   SKIP_SERVICE=1 ./deploy.sh                        # hoppa över systemd (kör bara kod+deps)

set -Eeuo pipefail

# ---- Konfiguration (kan överridas via env) ----------------------------------
BRANCH="${BRANCH:-main}"
BIND="${BIND:-127.0.0.1:5800}"
WORKERS="${WORKERS:-4}"
SERVICE="${SERVICE:-eystrasalt}"
ENV_DIR="${ENV_DIR:-/etc/eystrasalt}"
ENV_FILE="${ENV_FILE:-${ENV_DIR}/eystrasalt.env}"

# ---- Härled repo-katalog, användare, venv -----------------------------------
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
RUN_USER="${SUDO_USER:-$(id -un)}"
VENV="${REPO_DIR}/.venv"

# ---- Utskrifter -------------------------------------------------------------
log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mVARNING:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mFEL:\033[0m %s\n' "$*" >&2; exit 1; }
trap 'die "avbröt på rad $LINENO"' ERR

# ---- sudo bara om vi inte redan är root -------------------------------------
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
need() { command -v "$1" >/dev/null 2>&1 || die "saknar kommando: $1"; }

need git; need python3
[ -f "${REPO_DIR}/app.py" ] || die "hittar inte app.py i ${REPO_DIR} — kör scriptet i repot eller sätt REPO_DIR=…"
cd "$REPO_DIR"

# ---- 1. Uppdatera koden -----------------------------------------------------
log "Uppdaterar koden (branch: ${BRANCH})…"
if ! git diff --quiet || ! git diff --cached --quiet; then
  die "det finns oincheckade ändringar i ${REPO_DIR} — checka in eller stasha dem först (git stash)"
fi
git fetch --prune origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
log "På commit: $(git rev-parse --short HEAD)"

# ---- 2. Virtuell miljö + beroenden -----------------------------------------
log "Sätter upp virtuell miljö och installerar beroenden…"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r requirements.txt

# ---- 3. Smoke-test ----------------------------------------------------------
log "Smoke-test (importerar appen)…"
"$VENV/bin/python" -c "import app" || die "appen kunde inte importeras — se felet ovan"

# ---- 4. Seeda forskningsbiblioteket ----------------------------------------
log "Seedar forskningsbiblioteket…"
"$VENV/bin/python" -m ai.seed_reports || warn "seed misslyckades (fortsätter)"

# ---- 5. Hemligheter i root-skyddad env-fil ---------------------------------
if [ ! -f "$ENV_FILE" ]; then
  log "Skapar hemlighetsfil ${ENV_FILE} (0600, root)…"
  $SUDO mkdir -p "$ENV_DIR"
  admin_pw=""
  while [ -z "$admin_pw" ]; do
    read -rs -p "Sätt ADMIN_PASSWORD (lösenord för publikationer): " admin_pw; echo
    [ -n "$admin_pw" ] || warn "lösenordet får inte vara tomt"
  done
  read -rp "ANTHROPIC_API_KEY (valfritt — Enter för att hoppa över): " ai_key || true
  umask 077
  tmp="$(mktemp)"
  {
    echo "APP_ENV=production"
    echo "ADMIN_PASSWORD=${admin_pw}"
    echo "MAX_CONTENT_KB=512"
    [ -n "${ai_key:-}" ] && echo "ANTHROPIC_API_KEY=${ai_key}"
  } > "$tmp"
  $SUDO install -m 600 -o root -g root "$tmp" "$ENV_FILE"
  rm -f "$tmp"
  unset admin_pw ai_key
else
  log "Behåller befintlig hemlighetsfil ${ENV_FILE}"
fi

# ---- 6. systemd-tjänst (härdad) --------------------------------------------
if [ "${SKIP_SERVICE:-0}" = "1" ]; then
  warn "SKIP_SERVICE=1 — hoppar över systemd. Starta manuellt med:"
  echo "  ${VENV}/bin/gunicorn -w ${WORKERS} -b ${BIND} app:app   (med env ur ${ENV_FILE})"
  exit 0
fi

need systemctl
UNIT="/etc/systemd/system/${SERVICE}.service"
log "Skriver systemd-tjänst ${UNIT}…"
$SUDO tee "$UNIT" > /dev/null <<EOF
[Unit]
Description=Eystrasalt (Östersjö-simulering)
After=network.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV}/bin/gunicorn -w ${WORKERS} -b ${BIND} --timeout 120 app:app
Restart=always
RestartSec=3
# Härdning
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=${REPO_DIR}/data

[Install]
WantedBy=multi-user.target
EOF

log "Aktiverar och startar om tjänsten…"
$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SERVICE" >/dev/null 2>&1 || true
$SUDO systemctl restart "$SERVICE"

# ---- 7. Hälsokoll -----------------------------------------------------------
log "Hälsokoll mot http://${BIND}/api/defaults …"
ok=0
for i in 1 2 3 4 5 6 7 8; do
  sleep 2
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://${BIND}/api/defaults" || true)"
    [ "$code" = "200" ] && { ok=1; break; }
  else
    $SUDO systemctl is-active --quiet "$SERVICE" && { ok=1; break; }
  fi
done

if [ "$ok" = "1" ]; then
  log "Klart! Tjänsten '${SERVICE}' kör och svarar på http://${BIND}"
  $SUDO systemctl --no-pager --full status "$SERVICE" | head -n 6 || true
else
  die "tjänsten svarar inte — felsök med: sudo journalctl -u ${SERVICE} -n 60 --no-pager"
fi
