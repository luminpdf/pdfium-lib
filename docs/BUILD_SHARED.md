# Shared PDFium source (Lumin / rn-lumin-pdf)

This fork of **pdfium-lib** builds iOS and Android from **one** PDFium tree inside the **`pdfium-lib`** submodule:

| Role | Path (relative to `rn-lumin-pdf/`) |
|------|-------------------------------------|
| Source + edits | `pdfium-lib/pdfium/` (nested submodule) |
| gclient metadata | `pdfium-lib/build/shared/.gclient` |
| Build orchestration | `pdfium-lib/` (`make.py`, `modules/`) |
| iOS artifact staging | `pdfium-lib/build/ios/release/` |
| Android artifact staging | `pdfium-lib/build/android/release/` |
| App prebuilts | `ios/Vendor/`, `android/Vendor/` |

Set **`PDFIUM_SOURCE_DIR`** to an absolute path if `pdfium-lib/pdfium/` is not at the default location. All `make.py` tasks read it via `modules/pdfium_paths.py`.

---

## One-time setup

From the **rn-lumin-pdf** repo root:

```bash
git submodule update --init --recursive pdfium-lib

cd pdfium-lib
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export PATH="$PWD/build/depot-tools:$PATH"
python3 make.py build-depot-tools   # if build/depot-tools missing

export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
python3 make.py build-pdfium-shared
```

`build-pdfium-shared` writes `build/shared/.gclient` with **host-specific** `target_os` (`ios` on macOS, `android` on Linux), symlinks `build/shared/pdfium` → **`pdfium-lib/pdfium/`**, then runs `gclient sync` so DEPS land under **`$PDFIUM_SOURCE_DIR`**.

`build/ios/` and `build/android/` hold **release artifacts only** (no separate PDFium checkouts).

---

## Manual build (when `pnpm` scripts fail)

Always run **`make.py` from `pdfium-lib/`** with venv active and:

```bash
export PDFIUM_SOURCE_DIR="/absolute/path/to/rn-lumin-pdf/pdfium-lib/pdfium"
export PATH="/absolute/path/to/rn-lumin-pdf/pdfium-lib/build/depot-tools:$PATH"
```

### iOS (macOS + Xcode)

```bash
cd pdfium-lib
source .venv/bin/activate
export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
export PATH="$PWD/build/depot-tools:$PATH"

python3 make.py patch-ios
python3 make.py build-ios
python3 make.py install-ios
```

Install output: `build/ios/release/pdfium.xcframework`

Copy to the app (from repo root):

```bash
rm -rf ios/Vendor/pdfium.xcframework
cp -R pdfium-lib/build/ios/release/pdfium.xcframework ios/Vendor/
```

**Low-level (inside source):** after `patch-ios`, from `$PDFIUM_SOURCE_DIR`:

```bash
cd "$PDFIUM_SOURCE_DIR"
# Example: device arm64 release
gn gen out/ios-arm64-device-release --args='is_debug=false pdf_use_partition_alloc=false target_cpu="arm64" target_os="ios" ...'
ninja -C out/ios-arm64-device-release pdfium
```

Use the exact `--args` strings from `modules/common.py` → `get_build_args()` (same as `build-ios`).

### Android (Linux or Docker)

**Linux host:**

```bash
cd pdfium-lib
source .venv/bin/activate
export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
export PATH="$PWD/build/depot-tools:$PATH"

python3 make.py patch-android
# Optional once per machine:
bash "$PDFIUM_SOURCE_DIR/build/install-build-deps-android.sh"
python3 make.py build-android
python3 make.py install-android
```

Install output: `build/android/release/lib/<abi>/libpdfium.so` and `build/android/release/include/`

**macOS:** use Docker from repo root (`pnpm pdfium-build-android`) or mount `pdfium-lib/pdfium`:

```bash
docker run --rm --platform linux/amd64 \
  -v "$(pwd)/pdfium-lib:/app" \
  -v "$(pwd)/pdfium-lib/pdfium:/app/pdfium" \
  -e "PDFIUM_SOURCE_DIR=/app/pdfium" \
  -w /app pdfium-android-build \
  bash -lc 'export PATH=/opt/depot-tools:$PATH; python3 make.py patch-android && python3 make.py build-android && python3 make.py install-android'
```

**Low-level:** after `patch-android`, from `$PDFIUM_SOURCE_DIR`:

```bash
cd "$PDFIUM_SOURCE_DIR"
gn gen out/android-arm64-release --args='...'
ninja -C out/android-arm64-release pdfium
```

Built `.so` is under `out/android-<cpu>-release/libpdfium.so` (name may vary; `install-android` collects them).

---

## Switching iOS ↔ Android on one checkout

Platform patches edit the same files (`BUILD.gn`, etc.). Reset before changing platform:

```bash
# from repo root
pnpm pdfium-reset-patches
# or manually in pdfium-lib/pdfium/:
git checkout -- BUILD.gn public/fpdfview.h build/config/BUILDCONFIG.gn \
  build/config/ios/rules.gni core/fxge/BUILD.gn build/config/ios/ios_sdk_overrides.gni
```

Then run `patch-ios` or `patch-android` again.

---

## What changed in this pdfium-lib fork

| File | Change |
|------|--------|
| `modules/pdfium_paths.py` | Resolves `PDFIUM_SOURCE_DIR` / `pdfium-lib/pdfium/` |
| `modules/pdfium.py` | `get_pdfium_shared()` — single gclient root at `build/shared/` |
| `modules/ios.py`, `modules/android.py` | Build/patch/install use shared source; `out/` under `pdfium/out/` |
| `modules/patch.py` | Patches apply to shared tree |
| `make.py` | Task `build-pdfium-shared` |
| `.gitmodules` | Nested `pdfium` submodule |
| `docker/android/Dockerfile` | `target_os` includes iOS + Android for dep parity |

Legacy `build-pdfium-ios` / `build-pdfium-android` still call `get_pdfium_shared()` (not separate clones).

Parent repo docs: [`../../docs/pdfium.md`](../../docs/pdfium.md).
