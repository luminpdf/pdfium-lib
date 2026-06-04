# Shared PDFium source

One tree for iOS and Android: **`pdfium/`**. gclient uses **`build/shared/pdfium`** (symlink → `../../pdfium`). Artifacts: **`build/ios/release/`**, **`build/android/release/`**. Ninja: **`pdfium/out/`**.

## One-time setup

From **`pdfium-lib/`**:

```bash
git submodule update --init pdfium
python3 -m pip install -r requirements.txt
export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
python3 make.py build-pdfium-shared
```

`depot_tools` are installed automatically if missing. Branch/url: **`modules/config.py`**.

Optional override: **`export PDFIUM_SOURCE_DIR=/abs/path/to/pdfium`**

Platform builds do **not** run `gclient sync` (keeps your branch/edits). Re-run **`build-pdfium-shared`** if DEPS are missing.

## Switching iOS ↔ Android

Reset patched files in **`pdfium/`** before the other platform:

```bash
cd pdfium && git checkout -- BUILD.gn public/fpdfview.h build/config/BUILDCONFIG.gn \
  build/config/ios/rules.gni core/fxge/BUILD.gn build/config/ios/ios_sdk_overrides.gni
```

Then build iOS or Android (patch runs again).

See [BUILD_IOS.md](BUILD_IOS.md) · [BUILD_ANDROID.md](BUILD_ANDROID.md)
