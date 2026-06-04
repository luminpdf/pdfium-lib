# Build for iOS (Lumin shared source)

PDFium **source** lives in **`pdfium-lib/pdfium/`** (nested submodule). `build/ios/` holds release artifacts only.

Full manual steps: **[BUILD_SHARED.md](BUILD_SHARED.md)**.

## Quick path (from rn-lumin-pdf root)

```bash
pnpm pdfium-init-shared   # once
pnpm pdfium-build-ios
```

## make.py only (from `pdfium-lib/`)

Prerequisites: depot tools, venv, `PDFIUM_SOURCE_DIR` pointing at `pdfium-lib/pdfium/`.

```bash
cd pdfium-lib
source .venv/bin/activate
export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
export PATH="$PWD/build/depot-tools:$PATH"

python3 make.py build-pdfium-shared   # once: sync DEPS into pdfium/
python3 make.py patch-ios
python3 make.py build-ios
python3 make.py install-ios
python3 make.py test-ios              # optional
```

Output: `build/ios/release/pdfium.xcframework`

Copy into the React Native app:

```bash
cp -R build/ios/release/pdfium.xcframework ../ios/Vendor/
```

## Notes

- Run **make.py** with Python 3.
- Edit fork code under **`pdfium/`**, commit to `luminpdf-mobile/main`.
- Before building Android on the same machine, run **`pnpm pdfium-reset-patches`** (see BUILD_SHARED.md).
