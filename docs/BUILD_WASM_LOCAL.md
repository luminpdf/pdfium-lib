# Building PDFium WASM from Local Source

This guide explains how to build the PDFium WASM assets after making changes to the Lumin PDFium fork.

## Prerequisites

- Docker installed and running
- The `pdfium` submodule checked out at `packages/wasm/pdfium/` (the Lumin fork)

## Overview

The build uses Docker to compile PDFium into WebAssembly. The local PDFium source is copied into the Docker build context, then the full pipeline runs inside the container to avoid macOS case-insensitive filesystem issues.

**Build pipeline:**
1. `build-pdfium-wasm` — Copy PDFium source + sync Chromium dependencies via gclient
2. `patch-wasm` — Patch PDFium for Emscripten compatibility
3. `build-wasm` — Compile with gn + ninja
4. `install-wasm` — Install headers and static library
5. `test-wasm` — Test compilation with em++
6. `generate-wasm` — Generate JavaScript/WASM bindings (UMD, ESM, standalone)

## Step 1: Prepare Docker Build Context

Copy the PDFium source into the Docker build context directory:

```bash
cd packages/wasm/pdfium-lib
rm -rf docker/wasm/pdfium
cp -r ../../pdfium docker/wasm/pdfium
```

## Step 2: Build the Docker Image

This installs all build tools (depot_tools, Emscripten SDK, ninja, etc.) and pre-syncs PDFium dependencies. Only needs to be rebuilt when dependencies or tooling change.

**macOS arm64 (Apple Silicon):**
```bash
docker build --platform linux/amd64 -t pdfium-wasm -f docker/wasm/Dockerfile.patched docker/wasm
```

**Linux x86_64:**
```bash
docker build -t pdfium-wasm -f docker/wasm/Dockerfile.patched docker/wasm
```

> **Note:** Use `Dockerfile.patched` instead of `Dockerfile`. The patched version fixes a NodeSource apt script deprecation issue — see [Troubleshooting](#npm-not-found-during-docker-image-build) for details.

This takes ~10-15 minutes on first run. Subsequent builds use Docker layer cache.

## Step 3: Run the Full Build Pipeline

The build must run on the container's filesystem (not the host volume) because macOS's case-insensitive filesystem causes file collisions with Chromium's sysroot headers.

**macOS arm64:**
```bash
docker run --platform linux/amd64 -v "${PWD}:/app" pdfium-wasm bash -c '
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
```

**Linux x86_64:** Same command but without `--platform linux/amd64`.

## Step 4: Verify Outputs

After a successful build, outputs are in `build/emscripten/wasm/release/`:

```bash
ls -la build/emscripten/wasm/release/lib/    # libpdfium.a
ls -la build/emscripten/wasm/release/node/   # pdfium.js, pdfium.wasm, pdfium.esm.js, etc.
```

Expected files:
| File | Description |
|------|-------------|
| `libpdfium.a` | Static library (~11 MB) |
| `pdfium.js` + `pdfium.wasm` | UMD module |
| `pdfium.esm.js` + `pdfium.esm.wasm` | ES module |
| `pdfium.std.js` + `pdfium.std.wasm` | Standalone module |

## Quick Rebuild After Source Changes

If you've only changed PDFium source (not build tooling), you can skip rebuilding the Docker image and just re-run Step 1 (copy source) + Step 3 (build pipeline). The Docker image caches all build tools.

```bash
# 1. Copy updated source
rm -rf docker/wasm/pdfium && cp -r ../../pdfium docker/wasm/pdfium

# 2. Rebuild Docker image (fast — only the COPY layer changes)
docker build --platform linux/amd64 -t pdfium-wasm -f docker/wasm/Dockerfile.patched docker/wasm

# 3. Run build pipeline (Step 3 above)
```

## Troubleshooting

### `gn` fails with "python3_bin_reldir.txt not found"
The depot_tools `gn` wrapper needs bootstrapping. Ensure `/pdfium/buildtools/linux64` is on PATH before `/opt/depot-tools` so the real `gn` binary is used.

### `cp: cannot create regular file ... File exists`
macOS case-insensitive filesystem collision with Linux sysroot headers (e.g., `xt_CONNMARK.h` vs `xt_connmark.h`). This is why the build runs on the container's ext4 filesystem. These errors during the final copy-back are harmless — only the `wasm/` output directory is needed.

### `gclient sync` fails with "uncommitted changes"
The parent `.git` file (submodule pointer) confuses git. The build script hides it temporarily. If running manually, rename `.git` before running gclient.

### `npm: not found` during Docker image build

**Symptom:** Docker build fails at `RUN npm install -g npm@latest` with `/bin/sh: 1: npm: not found`.

**Root cause:** The original `Dockerfile` installs Node.js via NodeSource's APT setup script (`setup_22.x`). NodeSource has deprecated these scripts, and they no longer reliably install `npm` alongside `nodejs` on Ubuntu 22.04.

**Fix:** Use `Dockerfile.patched` instead of `Dockerfile`. The patched version removes the NodeSource dependency entirely and symlinks Node.js/npm from the Emscripten SDK (`/emsdk/node/*/bin/{node,npm,npx}`), which is already installed in the image.

```bash
# Use patched Dockerfile
docker build --platform linux/amd64 -t pdfium-wasm -f docker/wasm/Dockerfile.patched docker/wasm
```

### Const-correctness compilation errors in custom PDFium C API functions

**Symptom:** ninja build fails with errors like:
```
fpdf_annot.cpp: error: cannot initialize a variable of type 'const CPDF_Page *' with an rvalue of type 'IPDF_Page *'
fpdf_annot.cpp: error: 'this' argument to member function 'AsPDFPage' has type 'const CPDF_Page', but function is not marked const
fpdf_annot.cpp: error: cannot initialize a variable of type 'CPDF_Dictionary *' with an rvalue of type 'const CPDF_Dictionary *'
```

**Root cause:** When adding custom functions to the PDFium C API (e.g., in `fpdfsdk/fpdf_annot.cpp`), it's easy to use incorrect types that don't match upstream PDFium's API signatures. Common mistakes:

| Mistake | Correct usage |
|---------|---------------|
| `const CPDF_Page* p = ctx->GetPage()` | `IPDF_Page* p = ctx->GetPage()` — returns `IPDF_Page*`, not `CPDF_Page*` |
| `const CPDF_Page* p = page->AsPDFPage()` | `CPDF_Page* p = page->AsPDFPage()` — `AsPDFPage()` is non-const |
| `CPDF_Dictionary* d = ctx->GetAnnotDict()` | `RetainPtr<CPDF_Dictionary> d = ctx->GetMutableAnnotDict()` — use the mutable accessor when you need to modify the dict |

**Fix:** Check `cpdf_annotcontext.h` for the correct return types and const qualifiers. Use `GetMutableAnnotDict()` when the dictionary needs to be modified (e.g., calling `SetNewFor`).

### OOM during x86 emulation on Apple Silicon
The build runs under Rosetta/QEMU emulation. Ensure Docker has at least 8 GB of memory allocated (Docker Desktop → Settings → Resources).
