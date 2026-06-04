# Lumin fork notes (pdfium-lib)

This submodule is wired for **[rn-lumin-pdf](https://github.com/luminpdf/rn-lumin-pdf)** shared PDFium source.

## Where the code lives

- **You edit:** `pdfium/` (nested submodule inside this repo)
- **This repo runs:** `make.py`, `modules/*.py`, GN/Ninja via depot tools
- **`build/ios/`** and **`build/android/`** — release artifact staging only (no separate PDFium checkouts)

## Commands (parent repo)

```bash
pnpm pdfium-init-shared
pnpm pdfium-build-ios
pnpm pdfium-build-android
pnpm pdfium-reset-patches
```

## Manual build

See **[docs/BUILD_SHARED.md](docs/BUILD_SHARED.md)** when `pnpm` scripts fail.

Platform-specific shortcuts:

- [docs/BUILD_IOS.md](docs/BUILD_IOS.md)
- [docs/BUILD_ANDROID.md](docs/BUILD_ANDROID.md)

## Core changes in this submodule

- `modules/pdfium_paths.py` — `PDFIUM_SOURCE_DIR`, default `pdfium-lib/pdfium/`
- `modules/pdfium.py` — `get_pdfium_shared()`, `build/shared/` gclient
- `modules/ios.py`, `modules/android.py`, `modules/patch.py` — shared source paths
- `make.py` — `build-pdfium-shared` task
- `.gitmodules` — nested `pdfium` submodule

Commit changes **inside this submodule** (including `pdfium/` pointer updates), then bump the parent repo’s `pdfium-lib` submodule pointer.
