#!/usr/bin/env bash
# install.sh — deterministic, idempotent setup for the AutoSelf project
#
# Non-destructive upgrade of your original script. Adds:
# - Strict bash safety flags and friendly logging
# - OS/privilege checks, graceful sudo handling
# - Python 3.11 install on Ubuntu/WSL via deadsnakes PPA (only if missing)
# - Virtualenv creation/activation at .venv
# - Deterministic dependency install (prefers requirements-lock.txt when present)
# - Optional extras install for frontend/backend split if their files exist
# - Artifact directories bootstrap (results/, figs/)
#
# Re-run safe: if tools are installed and .venv exists, it simply reuses them.

set -euo pipefail
IFS=$'\n\t'

# -------------------------------
# Pretty helpers
# -------------------------------
log()   { printf "\033[1;34m[INFO]\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m[OK]\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()   { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*"; }

# Run a command with sudo if available and not root
SUDO=""
if command -v sudo >/dev/null 2>&1 && [ "${EUID:-$(id -u)}" -ne 0 ]; then
  SUDO="sudo"
fi

# -------------------------------
# Detect platform
# -------------------------------
OS_UNAME=$(uname -s || echo "Unknown")
IS_UBUNTU=false
IS_WSL=false
if [ -f /etc/os-release ]; then
  . /etc/os-release || true
  if echo "$ID $ID_LIKE" | grep -qi "ubuntu\|debian"; then
    IS_UBUNTU=true
  fi
fi
if grep -qi "microsoft" /proc/version 2>/dev/null; then
  IS_WSL=true
fi

log "Detected system: uname=$OS_UNAME, ubuntu=$IS_UBUNTU, wsl=$IS_WSL"

# -------------------------------
# Ensure Python 3.11 is available (Ubuntu/WSL path)
# -------------------------------
PY_BIN="python3.11"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  if $IS_UBUNTU; then
    log "Python 3.11 not found. Installing via apt (deadsnakes PPA)."
    $SUDO apt-get update -y
    $SUDO apt-get install -y software-properties-common curl ca-certificates
    if ! grep -q "deadsnakes" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
      $SUDO add-apt-repository -y ppa:deadsnakes/ppa || true
    fi
    $SUDO apt-get update -y
    $SUDO apt-get install -y python3.11 python3.11-venv python3.11-distutils
    ok "Python 3.11 installed."
  else
    warn "Python 3.11 not found and OS is not Ubuntu/Debian."
    warn "Please install Python 3.11 manually or use Dockerfile.repro."
    exit 1
  fi
else
  ok "Found $("$PY_BIN" -V 2>&1)"
fi

# -------------------------------
# Create / activate virtual environment
# -------------------------------
if [ -d ".venv" ]; then
  ok ".venv already exists — reusing it."
else
  log "Creating virtual environment at .venv (Python 3.11)"
  "$PY_BIN" -m venv .venv
  ok "Virtual environment created."
fi

# shellcheck source=/dev/null
. ./.venv/bin/activate
ok "Activated virtualenv: $(python -V 2>&1)"

# Make pip deterministic and quiet-er
export PIP_DISABLE_PIP_VERSION_CHECK=1
python -m pip install --upgrade pip setuptools wheel >/dev/null
ok "Upgraded pip/setuptools/wheel"

# -------------------------------
# Install dependencies
# -------------------------------
if [ -f "requirements-lock.txt" ]; then
  log "Installing pinned dependencies from requirements-lock.txt"
  pip install --no-deps -r requirements-lock.txt
elif [ -f "requirements.txt" ]; then
  log "Installing dependencies from requirements.txt"
  pip install -r requirements.txt
else
  warn "requirements(-lock).txt not found. Installing minimal runtime deps."
  pip install python-dotenv pyyaml pandas numpy matplotlib
fi

# Optional split requirements
if [ -f "requirements.backend.txt" ]; then
  log "Installing backend extras from requirements.backend.txt"
  pip install -r requirements.backend.txt || warn "Backend extras failed; continuing."
fi
if [ -f "requirements.frontend.txt" ]; then
  log "Installing frontend extras from requirements.frontend.txt"
  pip install -r requirements.frontend.txt || warn "Frontend extras failed; continuing."
fi

# -------------------------------
# Bootstrap artifact directories
# -------------------------------
mkdir -p results figs manuscript_results
ok "Created/verified artifact directories: results/, figs/, manuscript_results/"

# -------------------------------
# Final notes
# -------------------------------
ok "Environment setup complete."
log "To start the local stack:"
printf "  1) source .venv/bin/activate\n"
printf "  2) export SERVER_URL=http://localhost:8008\n"
printf "  3) python run.py\n"

# Exit cleanly
exit 0
