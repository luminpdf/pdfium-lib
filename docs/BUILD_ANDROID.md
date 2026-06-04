# Build for Android

1. First, complete [BUILD_SHARED.md](BUILD_SHARED.md) (one-time).

2. **Linux only** — install system packages for the NDK toolchain:
```bash
./pdfium/build/install-build-deps.sh --android
```
   On **macOS**, skip this step and use [Docker](#docker-macos-arm64) below (the image already runs it).

3. From **`pdfium-lib/`**:
```bash
source .venv/bin/activate   # optional
export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
python3 make.py build-android
python3 make.py install-android
```
   (output **`build/android/release/`** — `lib/<abi>/libpdfium.so`, `include/`)

4. Test (optional):
```bash
python3 make.py test-android
```

Obs:
- Run **`make.py`** with Python 3.
- Needs **Linux** (real, VM, or Docker).
- Edit fork under **`pdfium/`**; re-run **build** + **install** after changes.
- Before iOS on the same machine, reset patches — [BUILD_SHARED.md](BUILD_SHARED.md).
- Do **not** use **`build-pdfium-android`** with shared **`pdfium/`**.

## Docker

Copy the shared **`pdfium/`** submodule into the Docker build context (same pattern as [BUILD_WASM_LOCAL.md](BUILD_WASM_LOCAL.md)):

```bash
git submodule update --init pdfium
rm -rf docker/android/pdfium
rsync -a --exclude='.git' --exclude='third_party' --exclude='build' --exclude='out' --exclude='_bad_scm' pdfium/ docker/android/pdfium/
```

Build image:
```bash
docker build -t pdfium-android -f docker/android/Dockerfile docker/android
```

Run build + install (mount the **parent repo** so nested `pdfium/` submodule git metadata resolves):

```bash
docker run --rm \
  -v "$(cd .. && pwd):/workspace" \
  -w /workspace/pdfium-lib \
  pdfium-android \
  bash -lc 'export PDFIUM_SOURCE_DIR=/workspace/pdfium-lib/pdfium && python3 make.py build-android && python3 make.py install-android'
```

Re-run **`build-pdfium-shared`** inside the container if DEPS are missing:

```bash
docker run --rm \
  -v "$(cd .. && pwd):/workspace" \
  -w /workspace/pdfium-lib \
  pdfium-android \
  bash -lc 'export PDFIUM_SOURCE_DIR=/workspace/pdfium-lib/pdfium && python3 make.py build-pdfium-shared'
```

## Docker (macOS arm64)

Build image:
```bash
docker build --platform linux/amd64 -t pdfium-android -f docker/android/Dockerfile docker/android
```

Run build + install:
```bash
docker run --platform linux/amd64 --rm \
  -v "$(cd .. && pwd):/workspace" \
  -w /workspace/pdfium-lib \
  pdfium-android \
  bash -lc 'export PDFIUM_SOURCE_DIR=/workspace/pdfium-lib/pdfium && python3 make.py build-pdfium-shared && python3 make.py build-android && python3 make.py install-android'
```

Smoke test:
```bash
docker run --platform linux/amd64 --rm \
  -v "$(cd .. && pwd):/workspace" \
  -w /workspace/pdfium-lib \
  pdfium-android echo "test"
```
