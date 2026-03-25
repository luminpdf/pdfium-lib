# Building PDFium for macOS from Local Source

This guide explains how to build the PDFium macOS static library after making changes to the Lumin PDFium fork.

## Prerequisites

- macOS with Xcode command line tools installed (`xcode-select --install`)
- Python 3 with pip
- CMake (for running the test sample)
- The `pdfium` submodule checked out at `packages/wasm/pdfium/` (the Lumin fork)

### Install Python dependencies

```bash
cd packages/wasm/pdfium-lib
pip3 install -r requirements.txt
```

### Install depot_tools (first time only)

```bash
python3 make.py build-depot-tools
export PATH=$PATH:$PWD/build/depot-tools
```

Or if `build/depot-tools` already exists from a previous build:

```bash
export PATH=$PATH:$PWD/build/depot-tools
```

## Overview

The macOS build runs natively (no Docker required). It compiles PDFium for both x64 and arm64, then merges them into a universal binary with `lipo`.

**Build pipeline:**
1. `build-pdfium-macos` — Copy local PDFium source + sync Chromium dependencies via gclient
2. `patch-macos` — Patch PDFium for macOS compatibility
3. `build-macos` — Compile with gn + ninja (x64 and arm64)
4. `install-macos` — Merge into universal binary + copy headers
5. `test-macos` — Build and run sample program

## Step 1: Sync PDFium Source and Dependencies

This copies the local PDFium fork into `build/macos/pdfium/` and runs `gclient sync` to download Chromium build dependencies.

```bash
cd packages/wasm/pdfium-lib
export PATH=$PATH:$PWD/build/depot-tools
python3 make.py build-pdfium-macos
```

**Known issue:** If this fails with `fatal: not a git repository`, the copied `pdfium` directory still has a submodule `.git` pointer. Fix manually:

```bash
rm -rf build/macos/pdfium/.git
cd build/macos/pdfium && git init && git add . && git commit --allow-empty -m "local-build-sync"
cd ../../..
```

Then configure and sync gclient manually:

```bash
cd build/macos
gclient config --custom-var checkout_configuration=minimal --unmanaged pdfium
echo "target_os = [ 'macos' ]" >> .gclient
gclient sync --no-history --shallow
cd ../..
```

## Step 2: Patch

```bash
python3 make.py patch-macos
```

## Step 3: Build

Compiles PDFium for both `x64` and `arm64` architectures using gn + ninja.

```bash
python3 make.py build-macos
```

## Step 4: Install

Merges the per-architecture static libraries into a universal binary with `lipo` and copies public headers.

```bash
python3 make.py install-macos
```

## Step 5: Test

Builds and runs a sample program that loads a PDF and renders the first page.

```bash
python3 make.py test-macos
```

Expected output:
```
Starting...
Loading PDF...
Checking PDF...
Total of pages: 4
First page has size: 21cm X 27cm
Buffer size: 1938816
[OK]
```

## Verify Outputs

After a successful build, outputs are in `build/macos/release/`:

```bash
file build/macos/release/lib/libpdfium.a    # Universal binary (x86_64 + arm64)
ls -lh build/macos/release/lib/libpdfium.a  # ~24 MB
ls build/macos/release/include/             # Public headers
```

| Output | Description |
|--------|-------------|
| `build/macos/release/lib/libpdfium.a` | Universal static library (~24 MB, x86_64 + arm64) |
| `build/macos/release/include/` | Public C API headers |
| `build/macos/release/include/cpp/` | C++ wrapper headers |

## Quick Rebuild After Source Changes

If you've only changed PDFium source (not build tooling), you can skip `build-pdfium-macos` (gclient sync) and re-run from patch:

```bash
# Copy updated source over the existing build copy
rm -rf build/macos/pdfium
cp -r ../pdfium build/macos/pdfium
rm -rf build/macos/pdfium/.git
cd build/macos/pdfium && git init && git add . && git commit --allow-empty -m "local-build-sync" && cd ../../..

# Re-run from patch
python3 make.py patch-macos
python3 make.py build-macos
python3 make.py install-macos
python3 make.py test-macos
```

## One-liner (Full Build)

Run all steps sequentially after depot_tools is set up:

```bash
cd packages/wasm/pdfium-lib
export PATH=$PATH:$PWD/build/depot-tools
python3 make.py build-pdfium-macos && \
python3 make.py patch-macos && \
python3 make.py build-macos && \
python3 make.py install-macos && \
python3 make.py test-macos
```

## Troubleshooting

### `fatal: not a git repository` during `build-pdfium-macos`

The copied `pdfium` directory contains a `.git` file (submodule pointer) referencing a path that doesn't exist in the build directory. See the manual fix in Step 1 above.

### `gclient sync` fails with "uncommitted changes"

The parent `.git` file (submodule pointer) confuses gclient's git commands. The `pdfium.py` module hides it temporarily, but if running manually, rename `.git` before running gclient:

```bash
mv .git .git.bak
gclient sync --no-history --shallow
mv .git.bak .git
```

### `gn` or `ninja` not found

Ensure depot_tools is on your PATH:

```bash
export PATH=$PATH:$PWD/build/depot-tools
```

### Build fails on Apple Silicon

The build natively supports arm64 — no emulation needed. If you see architecture-related errors, ensure Xcode and the command line tools are up to date:

```bash
xcode-select --install
softwareupdate --install -a
```

## Sample

The sample Apple project is at `sample-apple/Sample.xcodeproj`.

To use the built library in the sample, copy the outputs:

```bash
cp -r build/macos/release/include sample-apple/SampleMac/Vendor/
cp -r build/macos/release/lib sample-apple/SampleMac/Vendor/
```
