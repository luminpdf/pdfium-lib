# Build for Android (Lumin shared source)

PDFium **source** lives in **`pdfium-lib/pdfium/`** (nested submodule). `build/android/` holds release artifacts only.

Full manual steps (Linux, Docker, low-level `gn`/`ninja`): **[BUILD_SHARED.md](BUILD_SHARED.md)**.

## Quick path (from rn-lumin-pdf root)

```bash
pnpm pdfium-init-shared    # once
pnpm pdfium-build-android  # Linux native or Docker on macOS
```

## make.py only (from `pdfium-lib/` on Linux)

```bash
cd pdfium-lib
source .venv/bin/activate
export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
export PATH="$PWD/build/depot-tools:$PATH"

python3 make.py build-pdfium-shared   # once
python3 make.py patch-android
bash "$PDFIUM_SOURCE_DIR/build/install-build-deps-android.sh"   # once per machine
python3 make.py build-android
python3 make.py install-android
python3 make.py test-android          # optional
```

Output: `build/android/release/lib/<abi>/libpdfium.so`, `build/android/release/include/`

Copy into the app (from repo root):

```bash
# or use pnpm pdfium-build-android which runs install_android_vendor
mkdir -p android/Vendor/pdfium/lib android/Vendor/pdfium/include
cp -R pdfium-lib/build/android/release/lib/* android/Vendor/pdfium/lib/
cp -R pdfium-lib/build/android/release/include/* android/Vendor/pdfium/include/
```

## Docker (macOS / non-Linux)

Build image (from `pdfium-lib/docker/android`):

```bash
docker build --platform linux/amd64 -t pdfium-android-build \
  -f docker/android/Dockerfile docker/android
```

Run with **`pdfium-lib`** mounted (includes nested **`pdfium/`**); see BUILD_SHARED.md.

Parent wrapper: `pnpm pdfium-build-android` from rn-lumin-pdf.

## Notes

- Run **make.py** with Python 3.
- Real Android builds need **Linux** (or Docker).
- Edit fork under **`pdfium/`**; reset patches when switching from iOS (BUILD_SHARED.md).
