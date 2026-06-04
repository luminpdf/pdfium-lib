# Build for iOS

1. First, complete [BUILD_SHARED.md](BUILD_SHARED.md) (one-time).

2. From **`pdfium-lib/`**:
```bash
source .venv/bin/activate   # optional
export PDFIUM_SOURCE_DIR="$(pwd)/pdfium"
python3 make.py build-ios
```
   (`patch-ios` + compile + `install-ios` — output **`build/ios/release/pdfium.xcframework`**)

3. Test (optional):
```bash
python3 make.py test-ios
```

Obs:
- Run **`make.py`** with Python 3.
- Edit fork under **`pdfium/`**; re-run **`build-ios`** to pick up changes.
- Before Android on the same machine, reset patches — [BUILD_SHARED.md](BUILD_SHARED.md).
- Do **not** use **`build-pdfium-ios`** with shared **`pdfium/`**.

## Sample

`sample-apple/Sample.xcodeproj` — copy **`build/ios/release/pdfium.xcframework`** to **`sample-apple/Sample/Vendor`**.
