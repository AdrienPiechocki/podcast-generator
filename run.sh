#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh — Lance le générateur de podcast
# Usage :
#   ./run.sh                        # sujet aléatoire
#   ./run.sh "Linux et la sécurité" # sujet personnalisé
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- Couleurs (désactivées si pas de terminal) ----------------------
if [ -t 1 ]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
  CYAN='\033[0;36m'; NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; NC=''
fi

log()  { echo -e "${CYAN}[run]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC}  $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[err]${NC}  $*" >&2; }

# ---------- Python ---------------------------------------------------------
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" &>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  err "Python introuvable. Installez Python 3.9+."
  exit 1
fi

PYTHON_VERSION=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log "Python détecté : $PYTHON ($PYTHON_VERSION)"

# ---------- Environnement virtuel ------------------------------------------
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  log "Création de l'environnement virtuel..."
  "$PYTHON" -m venv "$VENV_DIR"
fi

# Active le venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ---------- Dépendances Python ---------------------------------------------
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
  log "Installation / vérification des dépendances..."
  pip install --quiet --upgrade pip
  pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
  ok "Dépendances OK"
else
  warn "requirements.txt introuvable, passage sans installation."
fi

# ---------- Vérification Ollama --------------------------------------------
if ! command -v ollama &>/dev/null; then
  warn "Ollama n'est pas installé ou n'est pas dans le PATH."
  warn "Installez-le depuis https://ollama.com, puis : ollama pull gemma3n"
fi

# ---------- Vérification Piper TTS (optionnel) -----------------------------
if ! command -v piper-tts &>/dev/null; then
  warn "piper-tts non détecté : la génération audio sera ignorée."
  warn "Installez Piper depuis https://github.com/rhasspy/piper"
fi

# ---------- Téléchargement modèle Piper siwis-medium ----------------------
PIPER_BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"
PIPER_MODEL="fr_FR-siwis-medium.onnx"
PIPER_CONFIG="fr_FR-siwis-medium.onnx.json"

download_if_missing() {
  local file="$1"
  local url="$2"
  if [ ! -f "$SCRIPT_DIR/$file" ]; then
    log "Téléchargement de $file..."
    if command -v curl &>/dev/null; then
      curl -L --progress-bar -o "$SCRIPT_DIR/$file" "$url" \
        || { err "Échec du téléchargement de $file"; exit 1; }
    elif command -v wget &>/dev/null; then
      wget -q --show-progress -O "$SCRIPT_DIR/$file" "$url" \
        || { err "Échec du téléchargement de $file"; exit 1; }
    else
      err "curl et wget sont tous les deux absents. Impossible de télécharger $file."
      exit 1
    fi
    ok "$file téléchargé"
  else
    ok "$file déjà présent"
  fi
}

download_if_missing "$PIPER_MODEL"  "$PIPER_BASE_URL/$PIPER_MODEL"
download_if_missing "$PIPER_CONFIG" "$PIPER_BASE_URL/$PIPER_CONFIG"

# ---------- Lancement ------------------------------------------------------
log "Démarrage du générateur de podcast..."
echo ""

# Transmet tous les arguments à main.py (sujet optionnel)
"$PYTHON" "$SCRIPT_DIR/main.py" "$@"
