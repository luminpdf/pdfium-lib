#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PDFIUM_SRC="../pdfium"

if [ ! -d "$PDFIUM_SRC" ]; then
  echo "ERROR: PDFium source not found at $PDFIUM_SRC"
  echo "Ensure the pdfium submodule is checked out at packages/wasm/pdfium/"
  exit 1
fi

if ! docker info > /dev/null 2>&1; then
  echo "ERROR: Docker is not running. Start Docker Desktop and try again."
  exit 1
fi

PLATFORM_FLAG=""
if [ "$(uname -m)" = "arm64" ]; then
  PLATFORM_FLAG="--platform linux/amd64"
fi

# Step 1: Copy PDFium source into Docker build context
echo "=== Step 1: Copying PDFium source ==="
rm -rf docker/wasm/pdfium
cp -r "$PDFIUM_SRC" docker/wasm/pdfium

# Step 2: Build Docker image
echo "=== Step 2: Building Docker image ==="
docker build $PLATFORM_FLAG -t pdfium-wasm -f docker/wasm/Dockerfile docker/wasm

# Step 3: Run full build pipeline
echo "=== Step 3: Running build pipeline ==="
docker run $PLATFORM_FLAG -v "${PWD}:/app" pdfium-wasm bash -c '
set -e

export GIT_AUTHOR_NAME="build" GIT_AUTHOR_EMAIL="build@local"
export GIT_COMMITTER_NAME="build" GIT_COMMITTER_EMAIL="build@local"
export GCLIENT_SUPPRESS_GIT_VERSION_WARNING=1
export PATH=/pdfium/buildtools/linux64:$PATH

source /emsdk/emsdk_env.sh

BUILD_BASE=/tmp/pdfium-build
rm -rf $BUILD_BASE
mkdir -p $BUILD_BASE/app

# Copy app source (excluding build dir and .git) to container filesystem
cd /app
for f in $(ls -A | grep -v "^build$" | grep -v "^\.git$"); do
  cp -a "$f" $BUILD_BASE/app/ 2>/dev/null || true
done

cd $BUILD_BASE/app

# 1. build-pdfium-wasm: copy source + sync deps
mkdir -p build/emscripten
cp -a /pdfium build/emscripten/pdfium
cd build/emscripten/pdfium && rm -rf .git && git init && git add . && git commit --allow-empty -m "local-build-sync"
cd $BUILD_BASE/app/build/emscripten
gclient config --custom-var checkout_configuration=minimal --unmanaged pdfium
echo "target_os = [ '\''emscripten'\'' ]" >> .gclient
gclient sync --no-history --shallow

# 2-6. patch, build, install, test, generate
cd $BUILD_BASE/app
python3 make.py patch-wasm
python3 make.py build-wasm
python3 make.py install-wasm
python3 make.py test-wasm
python3 make.py generate-wasm

# Copy outputs back to host
rm -rf /app/build/emscripten/wasm
mkdir -p /app/build/emscripten/wasm
cp -a $BUILD_BASE/app/build/emscripten/wasm/. /app/build/emscripten/wasm/
echo "=== BUILD COMPLETE ==="
'

echo ""
echo "Outputs:"
ls -lh build/emscripten/wasm/release/lib/libpdfium.a
ls -lh build/emscripten/wasm/release/node/pdfium.wasm
echo ""
echo "Done! Assets are in build/emscripten/wasm/release/"
