#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh — Launch the podcast generator
# Usage:
#   ./run.sh                          # random topic
#   ./run.sh "Linux and security"     # custom topic
#   ./run.sh --lang en "Open Source"  # custom language + topic
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- Colors (disabled if not a terminal) ----------------------------
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
    err "Python not found. Please install Python 3.9+."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log "Python detected: $PYTHON ($PYTHON_VERSION)"

# ---------- Virtual environment --------------------------------------------
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

# Activate the venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ---------- Python dependencies --------------------------------------------
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    log "Installing / verifying dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
    ok "Dependencies OK"
else
    warn "requirements.txt not found, skipping installation."
fi

# ---------- Ollama check ---------------------------------------------------
if ! command -v ollama &>/dev/null; then
    warn "Ollama is not installed or not in PATH."
    warn "Install it from https://ollama.com, then run: ollama pull gemma3n"
fi

# ---------- Piper TTS check (optional) ------------------------------------
if ! command -v piper-tts &>/dev/null; then
    warn "piper-tts not detected: audio generation will be skipped."
    warn "Install Piper from https://github.com/rhasspy/piper"
fi

# ---------- Piper model download -------------------------------------------
# Each entry is: "filename|base_url"
# The .onnx and its .onnx.json config are downloaded automatically for each.
PIPER_HF="https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_MODELS=(
    # French
    "fr_FR-siwis-medium.onnx|$PIPER_HF/fr/fr_FR/siwis/medium"
    # English
    "en_US-lessac-medium.onnx|$PIPER_HF/en/en_US/lessac/medium"
)

MODELS_DIR="$SCRIPT_DIR/models"
mkdir -p "$MODELS_DIR"

download_if_missing() {
    local dest="$1"
    local url="$2"
    local name
    name="$(basename "$dest")"
    if [ ! -f "$dest" ]; then
        log "Downloading $name..."
        if command -v curl &>/dev/null; then
            curl -L --progress-bar -o "$dest" "$url" \
                || { err "Failed to download $name"; exit 1; }
        elif command -v wget &>/dev/null; then
            wget -q --show-progress -O "$dest" "$url" \
                || { err "Failed to download $name"; exit 1; }
        else
            err "Neither curl nor wget found. Cannot download $name."
            exit 1
        fi
        ok "$name downloaded"
    else
        ok "$name already present"
    fi
}

log "Checking Piper voice models..."
for entry in "${PIPER_MODELS[@]}"; do
    model_file="${entry%%|*}"
    base_url="${entry##*|}"
    download_if_missing "$MODELS_DIR/$model_file"       "$base_url/$model_file"
    download_if_missing "$MODELS_DIR/$model_file.json"  "$base_url/$model_file.json"
done

# ---------- Launch ---------------------------------------------------------
log "Starting podcast generator..."
echo ""

# Forward all arguments to main.py (optional topic / flags)
"$PYTHON" "$SCRIPT_DIR/main.py" "$@"