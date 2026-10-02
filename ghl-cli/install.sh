#!/usr/bin/env bash
# One-shot installer for the GoHighLevel CLI.
# Creates a local .venv, installs the package, initializes a credential profile,
# and prints next steps.

set -e

cd "$(dirname "$0")"

usage() {
  cat <<'EOF'
Usage: ./install.sh [--dev]

Install the GoHighLevel CLI into the repo-local .venv.

Options:
  --dev   Also install the pytest development dependencies.
  -h, --help
          Show this help message.
EOF
}

INSTALL_DEV=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dev) INSTALL_DEV=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "install.sh: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

# Pick a Python >= 3.10: $PYTHON override first, then the newest python3.x on
# PATH, then bare python3. macOS ships python3 = 3.9, so a stock Mac with a
# Homebrew python3.12 must not fail here.
pick_python() {
  if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return; fi
  for v in 3.14 3.13 3.12 3.11 3.10; do
    if command -v "python$v" >/dev/null 2>&1; then echo "python$v"; return; fi
  done
  echo "python3"
}
PY=$(pick_python)

echo "→ checking python ($PY)..."
"$PY" -c "import sys; assert sys.version_info >= (3, 10), 'need python 3.10+ (found ' + sys.version.split()[0] + ') — install one (e.g. brew install python) or set PYTHON=/path/to/python3.1x'"

if [ ! -d .venv ]; then
  echo "→ creating .venv ..."
  "$PY" -m venv .venv
fi

if [ "$INSTALL_DEV" -eq 1 ]; then
  INSTALL_TARGET=".[dev]"
  echo "→ installing package and development test dependencies ..."
else
  INSTALL_TARGET="."
  echo "→ installing package ..."
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -e "$INSTALL_TARGET" >/dev/null

chmod +x ghl

CONF_DIR="${GHL_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/ghl}"
CONFIG_FILE="$CONF_DIR/config"
PROFILE_DIR="$CONF_DIR/profiles"
PROFILE_NAME=""
PROFILE_FILE=""

# Profile files contain credentials. New directories and files should be
# private, but never change or replace permissions/content that already exist.
OLD_UMASK=$(umask)
umask 077
mkdir -p "$PROFILE_DIR"

if [ -f "$CONFIG_FILE" ]; then
  PROFILE_NAME=$(sed -n 's/^default_profile=//p' "$CONFIG_FILE" | head -1 | tr -d '[:space:]')
else
  PROFILE_NAME="default"
  printf 'default_profile=%s\n' "$PROFILE_NAME" > "$CONFIG_FILE"
  echo "→ created profile selector at $CONFIG_FILE"
fi

case "$PROFILE_NAME" in
  "")
    echo "→ existing $CONFIG_FILE has no default_profile; leaving profile selection unchanged"
    ;;
  *[!A-Za-z0-9._-]*)
    echo "→ existing default_profile is not a safe filename; leaving profiles unchanged"
    PROFILE_NAME=""
    ;;
  *)
    PROFILE_FILE="$PROFILE_DIR/$PROFILE_NAME.env"
    if [ ! -e "$PROFILE_FILE" ]; then
      cp .env.example "$PROFILE_FILE"
      chmod 600 "$PROFILE_FILE"
      echo "→ created credential profile template at $PROFILE_FILE"
    else
      echo "→ using existing credential profile at $PROFILE_FILE (unchanged)"
    fi
    ;;
esac
umask "$OLD_UMASK"

echo
echo "✓ installed."
echo
echo "Next steps:"
if [ -n "$PROFILE_FILE" ]; then
  echo "  1. Edit $PROFILE_FILE"
  echo "     Set GHL_API_KEY and GHL_LOCATION_ID at minimum."
else
  echo "  1. Set default_profile in $CONFIG_FILE, then create"
  echo "     $PROFILE_DIR/<profile>.env from .env.example."
fi
echo "  2. Run:        ./ghl contacts list --limit 5"
echo "  3. Optional:   to build/update workflows (internal API), grab your"
echo "                 Firebase token with the DevTools snippet in"
echo "                 docs/get-firebase-token.md and set GHL_FIREBASE_REFRESH_TOKEN."
echo
