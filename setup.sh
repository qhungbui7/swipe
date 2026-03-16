#!/bin/bash
# ── Bumble Smart Swipe — one-time setup ──────────────────────────────────────
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📁 Project dir: $DIR"
mkdir -p "$DIR/models"        # Ollama model storage
mkdir -p "$DIR/cache/screens" # screenshot cache

# ── Python deps ───────────────────────────────────────────────────────────────
VENV="/Users/qhungbui7/workspace/env/sandbox"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

echo "📦 Installing Python dependencies into $VENV…"
uv pip install --python "$PYTHON" playwright ollama psutil Pillow
"$PYTHON" -m playwright install chrome

# ── Ollama ────────────────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  echo "📥 Installing Ollama…"
  brew install ollama
fi

# Tell Ollama to store models inside this project folder
export OLLAMA_MODELS="$DIR/models"

# Start Ollama server in background (only if not already running)
if ! pgrep -x ollama &>/dev/null; then
  echo "🚀 Starting Ollama server…"
  OLLAMA_MODELS="$DIR/models" ollama serve &>/dev/null &
  sleep 3
fi

# Pull the vision model — qwen3-vl:4b is the newest SOTA (Oct 2025)
echo "📥 Pulling qwen3-vl:4b vision model (~3.0 GB)…"
OLLAMA_MODELS="$DIR/models" ollama pull qwen3-vl:4b

echo ""
echo "✅  Setup complete!"
echo ""
echo "To run:"
echo "  cd $DIR && python smart_swipe.py"
