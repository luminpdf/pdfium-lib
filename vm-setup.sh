#!/usr/bin/env bash
# vm-setup.sh — Provision an OrbStack Ubuntu ARM64 VM for PDFium WASM builds.
# Idempotent: safe to re-run. Installs all deps matching docker/wasm/Dockerfile.
#
# Usage (inside the VM):
#   chmod +x vm-setup.sh && ./vm-setup.sh
#
# After running, source your shell to pick up PATH changes:
#   source ~/.bashrc

set -euo pipefail

EMSDK_VERSION="4.0.15"
DEPOT_TOOLS_DIR="/opt/depot-tools"
EMSDK_DIR="/emsdk"
NODE_MAJOR=22

echo "=== PDFium WASM VM Setup ==="
echo "Target: Ubuntu ARM64 (OrbStack)"
echo ""

# Must run as root or with sudo
if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: Run with sudo or as root."
  exit 1
fi

# Detect the real user (if run via sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

# ── 1. System packages ──────────────────────────────────────────────
echo "=== Installing system packages ==="
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y --no-install-recommends \
  build-essential sudo file git wget curl cmake ninja-build zip unzip tar \
  python3 python3-pip python3-setuptools \
  nano lsb-release libglib2.0-dev tzdata doxygen

# Java 8 (needed by depot_tools/gclient)
# Create dummy keytool to avoid interactive prompts during install
echo '#!/bin/bash
exit 0' > /usr/local/bin/keytool && chmod +x /usr/local/bin/keytool
apt-get install -y --no-install-recommends openjdk-8-jdk
rm -f /usr/local/bin/keytool

# Ensure python3 is available as "python"
if [ ! -f /usr/bin/python ]; then
  ln -s /usr/bin/python3 /usr/bin/python
fi

echo "  [OK] System packages installed"

# ── 2. Google depot_tools ────────────────────────────────────────────
echo "=== Installing depot_tools ==="
if [ -d "$DEPOT_TOOLS_DIR" ]; then
  echo "  depot_tools already exists at $DEPOT_TOOLS_DIR — updating"
  git -C "$DEPOT_TOOLS_DIR" pull --ff-only || true
else
  git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git -b main "$DEPOT_TOOLS_DIR"
fi

echo "  [OK] depot_tools at $DEPOT_TOOLS_DIR"

# ── 3. Emscripten SDK ───────────────────────────────────────────────
echo "=== Installing Emscripten SDK $EMSDK_VERSION ==="
if [ -d "$EMSDK_DIR" ]; then
  echo "  emsdk already exists at $EMSDK_DIR"
else
  git clone https://github.com/emscripten-core/emsdk.git "$EMSDK_DIR"
fi

cd "$EMSDK_DIR"
./emsdk install "$EMSDK_VERSION"
./emsdk activate "$EMSDK_VERSION"

# Cache Emscripten system libraries (same as Dockerfile)
echo "  Caching Emscripten system libraries..."
source "$EMSDK_DIR/emsdk_env.sh"
echo "int main() { return 0; }" > /tmp/main.cc
em++ -s USE_ZLIB=1 -s USE_LIBJPEG=1 -s USE_PTHREADS=1 -s ASSERTIONS=1 -o /tmp/main.html /tmp/main.cc
rm -f /tmp/main.cc /tmp/main.html /tmp/main.js /tmp/main.wasm /tmp/main.worker.js

echo "  [OK] emsdk $EMSDK_VERSION at $EMSDK_DIR"

# ── 4. Node.js ───────────────────────────────────────────────────────
echo "=== Installing Node.js $NODE_MAJOR ==="
if command -v node &>/dev/null; then
  CURRENT_NODE=$(node --version | cut -d. -f1 | tr -d 'v')
  if [ "$CURRENT_NODE" -ge "$NODE_MAJOR" ]; then
    echo "  Node.js $(node --version) already installed — skipping"
  else
    echo "  Upgrading Node.js from v$CURRENT_NODE to v$NODE_MAJOR"
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
    apt-get install -y nodejs
  fi
else
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
  apt-get install -y nodejs
fi

npm install -g npm@latest 2>/dev/null || true

echo "  [OK] Node.js $(node --version)"

# ── 5. Python packages ──────────────────────────────────────────────
echo "=== Installing Python packages ==="
pip3 install --upgrade pip 2>/dev/null || true
pip3 install setuptools docopt pygemstones

echo "  [OK] Python packages"

# ── NOTE: PDFium build-deps ─────────────────────────────────────────
# The Dockerfile also runs pdfium/build/install-build-deps.sh to install
# additional Chromium build dependencies. This script cannot run it here
# because the pdfium source (with build/) is only available after the
# first `python3 make.py build-pdfium-wasm` (gclient sync).
#
# After your first gclient sync, run manually if the build fails:
#   cd build/emscripten/pdfium && echo n | ./build/install-build-deps.sh
# This installs system-level deps (libdrm, libx11, etc.) that PDFium needs.

# ── 6. Shell environment ────────────────────────────────────────────
echo "=== Configuring shell environment ==="
BASHRC="$REAL_HOME/.bashrc"
MARKER="# --- PDFium WASM build environment ---"

if grep -qF "$MARKER" "$BASHRC" 2>/dev/null; then
  echo "  .bashrc already configured — skipping"
else
  cat >> "$BASHRC" << 'ENVBLOCK'

# --- PDFium WASM build environment ---
export DEPOT_TOOLS_UPDATE=0
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export PATH="$PATH:/opt/depot-tools"
export PATH="$PATH:/emsdk:/emsdk/upstream/emscripten"
export EMSDK="/emsdk"
export PYTHONIOENCODING="utf8"
export LC_ALL=C.UTF-8

# Java 8
export JAVA_HOME="/usr/lib/jvm/java-8-openjdk-arm64"
export PATH="$PATH:$JAVA_HOME/bin"

# Source emsdk env (activates emcc/em++)
source /emsdk/emsdk_env.sh 2>/dev/null

# Convenience: navigate to pdfium-lib on the Mac mount
# Adjust the path below to match your Mac username/location
# alias cdpdfium='cd /mnt/mac/Users/<username>/Developer/pdf-sdk/lumin-pdf-sdk/packages/wasm/pdfium-lib'

# Fast iteration: rebuild after C++ changes
# alias pdfium-rebuild='cd pdfium && ninja -C out/emscripten-wasm-release pdfium && cd .. && python3 make.py install-wasm && python3 make.py generate-wasm'
# --- End PDFium WASM ---
ENVBLOCK

  echo "  [OK] .bashrc updated for $REAL_USER"
fi

# ── 7. Verify installation ──────────────────────────────────────────
echo ""
echo "=== Verification ==="
echo -n "  gcc:         " && gcc --version | head -1
echo -n "  cmake:       " && cmake --version | head -1
echo -n "  ninja:       " && ninja --version
echo -n "  python3:     " && python3 --version
echo -n "  node:        " && node --version
echo -n "  npm:         " && npm --version
echo -n "  java:        " && java -version 2>&1 | head -1
echo -n "  gn:          " && gn --version 2>/dev/null || echo "(available after sourcing .bashrc)"
echo -n "  emcc:        " && emcc --version 2>/dev/null | head -1 || echo "(available after sourcing .bashrc)"

echo ""
echo "=============================================="
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. source ~/.bashrc"
echo "    2. cd /mnt/mac/Users/<you>/.../packages/wasm/pdfium-lib"
echo "    3. python3 make.py build-pdfium-wasm   (first-time gclient sync)"
echo "    4. python3 make.py patch-wasm"
echo "    5. python3 make.py build-wasm"
echo "    6. python3 make.py install-wasm"
echo "    7. python3 make.py test-wasm"
echo "    8. python3 make.py generate-wasm"
echo ""
echo "  For fast iteration after C++ changes:"
echo "    cd pdfium && ninja -C out/emscripten-wasm-release pdfium"
echo "    cd .. && python3 make.py install-wasm && python3 make.py generate-wasm"
echo "=============================================="
