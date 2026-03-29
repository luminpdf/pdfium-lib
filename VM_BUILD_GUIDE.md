# PDFium WASM Build — OrbStack VM Guide

Build PDFium WASM using a native ARM64 Ubuntu VM in OrbStack. This replaces the Docker-based `build-wasm.sh` for local development, giving you fast incremental rebuilds when iterating on the `pdfium/` C++ fork.

## Why VM Instead of Docker?

The Docker pipeline (`build-wasm.sh`) uses an `ubuntu:22.04` **amd64** image. On Apple Silicon, Docker must emulate x86 via Rosetta/QEMU — making GN+Ninja builds painfully slow. The VM approach runs **native ARM64**, so compilation is at full speed and `ninja` incremental rebuilds take seconds instead of minutes.

## Prerequisites

- **macOS with Apple Silicon** (M1/M2/M3/M4)
- **[OrbStack](https://orbstack.dev/)** installed
- The `pdfium` submodule checked out at `packages/wasm/pdfium/`

---

## 1. Create the VM

```bash
orb create ubuntu:22.04 my-build-vm
```

> **Important:** Always specify `ubuntu:22.04`. Using `ubuntu` without a version tag gives the latest release (e.g., 25.10), which lacks `openjdk-8-jdk` required by depot_tools.

OrbStack automatically mounts your Mac filesystem at `/mnt/mac/`.

SSH in:

```bash
orb shell my-build-vm
```

## 2. Run the Setup Script

From inside the VM:

```bash
cd /mnt/mac/Users/<your-username>/Developer/pdf-sdk/lumin-pdf-sdk/packages/wasm/pdfium-lib
sudo ./vm-setup.sh
source ~/.bashrc
```

The script is **idempotent** (safe to re-run) and installs everything matching `docker/wasm/Dockerfile`:

| Dependency | Version | Location |
|-----------|---------|----------|
| build-essential, cmake, ninja | System packages | apt |
| Google depot_tools (gclient, gn) | latest | `/opt/depot-tools` |
| Emscripten SDK | 4.0.15 | `/emsdk` |
| Node.js | 22.x | apt (nodesource) |
| Python 3 + docopt + pygemstones | 3.10.x | apt + pip |
| OpenJDK | 8 | apt |
| doxygen | System | apt |

After setup, verify tools are available:

```bash
emcc --version    # should show 4.0.15
gn --version      # should print a hash
node --version    # should show v22.x
```

---

## 3. First-Time Full Build

Navigate to pdfium-lib via the Mac mount:

```bash
cd /mnt/mac/Users/<your-username>/Developer/pdf-sdk/lumin-pdf-sdk/packages/wasm/pdfium-lib
```

Run the full pipeline:

```bash
# 1. Copy pdfium source + gclient sync (fetches build deps: buildtools, third_party, etc.)
#    Slowest step (~10-20 min first time). Only needed once.
python3 make.py build-pdfium-wasm

# 2. Install PDFium's Chromium build dependencies (system-level libs)
#    Only available after gclient sync populates the build/ directory.
cd build/emscripten/pdfium && echo n | sudo ./build/install-build-deps.sh; cd -

# 3. Patch GN files for Emscripten target
python3 make.py patch-wasm

# 4. GN generate + Ninja compile → libpdfium.a
python3 make.py build-wasm

# 5. Copy libpdfium.a + headers to install dir
python3 make.py install-wasm

# 6. Test compile with em++
python3 make.py test-wasm

# 7. Generate final .js/.wasm outputs (UMD, ESM, standalone)
python3 make.py generate-wasm
```

### Build Outputs

All outputs land in `build/emscripten/wasm/release/`:

```
build/emscripten/wasm/release/
├── lib/
│   └── libpdfium.a          # Static PDFium library (~11 MB)
├── include/                  # PDFium public C headers
├── node/
│   ├── pdfium.wasm           # Main WASM binary (~3.8 MB)
│   ├── pdfium.js             # UMD (CommonJS/AMD) module
│   ├── pdfium.esm.js         # ES module
│   ├── pdfium.esm.wasm       # ES module WASM
│   ├── pdfium.std.js         # Standalone module
│   └── pdfium.std.wasm       # Standalone WASM
└── package.json
```

---

## 4. Fast Iteration (After C++ Changes)

This is the main benefit of the VM approach. Edit C++ on your Mac, rebuild in the VM in seconds.

### Changed C++ source in pdfium/ (most common)

```bash
# Ninja only recompiles changed .cpp files — takes seconds, not minutes
cd build/emscripten/pdfium
ninja -C out/emscripten-wasm-release pdfium

# Then reinstall + regenerate WASM outputs
cd /mnt/mac/Users/<your-username>/Developer/pdf-sdk/lumin-pdf-sdk/packages/wasm/pdfium-lib
python3 make.py install-wasm
python3 make.py generate-wasm
```

### Changed GN build files

If you modified any `BUILD.gn` files, re-run from patch:

```bash
python3 make.py patch-wasm
python3 make.py build-wasm
python3 make.py install-wasm
python3 make.py generate-wasm
```

### Changed public headers only

If you only added/modified PDFium public headers (no .cpp changes):

```bash
python3 make.py install-wasm
python3 make.py generate-wasm
```

### Convenience Alias

Uncomment in `~/.bashrc` (added by `vm-setup.sh`) or add manually:

```bash
alias pdfium-rebuild='cd build/emscripten/pdfium && ninja -C out/emscripten-wasm-release pdfium && cd /mnt/mac/Users/<your-username>/.../pdfium-lib && python3 make.py install-wasm && python3 make.py generate-wasm'
```

Then just run `pdfium-rebuild` after any C++ change.

---

## 5. Troubleshooting

### `gclient: command not found`

depot_tools isn't in your PATH:
```bash
source ~/.bashrc
echo $PATH | grep depot-tools   # verify
```

### `emcc: command not found`

Emscripten SDK not activated:
```bash
source /emsdk/emsdk_env.sh
```

### gclient sync fails with git errors

The `build-pdfium-wasm` step temporarily renames the `.git` file in `pdfium-lib/` (it's a submodule pointer). If it fails mid-way, the backup may be left behind:
```bash
# In pdfium-lib/ directory on your Mac
mv .git.bak .git   # restore if backup was left
```

### `JAVA_HOME` not set or wrong architecture

The setup script configures `JAVA_HOME` for ARM64. Verify:
```bash
echo $JAVA_HOME
# Should be: /usr/lib/jvm/java-8-openjdk-arm64
ls $JAVA_HOME/bin/java
```

### Permission errors on `/mnt/mac/`

OrbStack mounts use your Mac user's permissions. Always run `make.py` and `ninja` as your **regular user** (not root). Only use `sudo` for `vm-setup.sh` and `install-build-deps.sh`.

### Ninja reports "no work to do" but code changed

Ninja tracks file modification times. If your editor's save doesn't update mtime (rare):
```bash
touch path/to/changed/file.cpp
ninja -C out/emscripten-wasm-release pdfium
```

### Wrong Ubuntu version (no openjdk-8-jdk)

If you created the VM with `orb create ubuntu` (no version tag), you may have Ubuntu 25.x which lacks Java 8. Delete and recreate:
```bash
orb delete my-build-vm
orb create ubuntu:22.04 my-build-vm
sudo ./vm-setup.sh
```

---

## 6. VM Management

```bash
# Stop the VM (preserves all state including build artifacts)
orb stop my-build-vm

# Start it again
orb start my-build-vm

# SSH back in
orb shell my-build-vm

# Run a single command without interactive shell
orb run -m my-build-vm ninja --version

# Delete and recreate from scratch
orb delete my-build-vm
orb create ubuntu:22.04 my-build-vm
sudo ./vm-setup.sh
```

---

## 7. Docker vs VM — When to Use Which

| Scenario | Use |
|----------|-----|
| Iterating on `pdfium/` C++ code | **VM** — fast incremental ninja rebuilds |
| CI/CD or reproducible release builds | **Docker** (`build-wasm.sh`) — hermetic environment |
| First-time setup without OrbStack | **Docker** — no extra tools needed |
| Need to rebuild from scratch often | **Docker** — disposable containers |
| Debugging build failures interactively | **VM** — persistent state, can inspect freely |

---

## Quick Reference

```bash
# One-time setup
orb create ubuntu:22.04 my-build-vm
orb shell my-build-vm
sudo ./vm-setup.sh && source ~/.bashrc

# First build
python3 make.py build-pdfium-wasm
cd build/emscripten/pdfium && echo n | sudo ./build/install-build-deps.sh; cd -
python3 make.py patch-wasm && python3 make.py build-wasm
python3 make.py install-wasm && python3 make.py test-wasm && python3 make.py generate-wasm

# Fast iteration (after C++ changes)
cd build/emscripten/pdfium && ninja -C out/emscripten-wasm-release pdfium
cd <pdfium-lib-dir> && python3 make.py install-wasm && python3 make.py generate-wasm
```
