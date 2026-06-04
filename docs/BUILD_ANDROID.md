# Build for Android

1. First, complete [BUILD_SHARED.md](BUILD_SHARED.md) on **Linux** (one-time).

2. Install PDFium build deps:
```bash
./pdfium/build/install-build-deps-android.sh
```

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

Build image:
```bash
docker build -t pdfium-android -f docker/android/Dockerfile docker/android
```

Run:
```bash
docker run --rm -v ${PWD}:/app -w /app pdfium-android \
  bash -lc 'export PDFIUM_SOURCE_DIR=/app/pdfium && python3 make.py build-android && python3 make.py install-android'
```

## Docker (macOS arm64)

```bash
docker build --platform linux/amd64 -t pdfium-android -f docker/android/Dockerfile docker/android
docker run --platform linux/amd64 --rm -v ${PWD}:/app -w /app pdfium-android echo "test"
```
