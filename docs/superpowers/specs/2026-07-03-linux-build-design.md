# Linux Build for PDFium — Design

## Goal

Add a Linux target to this project's build pipeline, producing a shared library (`libpdfium.so`) for x64 and arm64, for use as a native library in a Linux app/server. This closes one of the two items on the README roadmap ("Linux, Windows").

## Non-goals

- Windows build (separate roadmap item, not part of this design).
- V8/XFA (forms) support — no existing platform enables it by default; Linux follows the same default.
- A `docker/linux/Dockerfile` for CI — no existing workflow (iOS, macOS, Android, WASM) runs its build inside Docker in CI; the `docker/android` and `docker/wasm` images exist purely as local-dev convenience. Local dev/testing for Linux will use an OrbStack Linux VM instead (see below), so no Dockerfile is needed for this project.

## Targets and portability approach

Targets: `x64` and `arm64`, matching the macOS target list shape (two architectures, no more).

**Portability approach: Approach A — portable build.**

Because the resulting `.so` is meant to be linked into a consumer's Linux app or server whose OS/distro isn't controlled by this project, building directly on the CI runner's default Ubuntu image (glibc ~2.39) would make the artifact fail with `GLIBC_2.xx not found` on older but still common deployment targets (Ubuntu 20.04, RHEL 8, etc.). To avoid that:

- Compile against an older glibc baseline than the CI runner's default (exact base image/version to be pinned during implementation — e.g. an older Ubuntu LTS).
- Statically link the C++ runtime: `-static-libstdc++ -static-libgcc`, so the artifact doesn't depend on the consumer's libstdc++ version.
- Bundle FreeType into the library (`pdf_bundle_freetype=true`, matching how the Android target already avoids depending on the host's system FreeType/fontconfig).

Net result: one self-contained `.so` per architecture that only depends on glibc (built against an old-enough baseline) and standard system libraries, not on the specific build machine's toolchain versions.

This was chosen as the default without an explicit user confirmation (the clarifying question went unanswered) because it directly matches the stated use case (an app/server whose deployment environment isn't specified) and is the safer default to build around. **Flag during spec review if a simpler build (straight on `ubuntu-24.04`, accepting a modern-glibc requirement) is preferred instead** — that would drop the static-linking/old-baseline work and bundled-FreeType requirement.

## Module structure

Mirrors `modules/android.py`, not `modules/macos.py` — both Linux and Android are shared-library, multi-architecture targets with no equivalent of `lipo`'s universal-binary merge (Linux has no fat-binary format), so each architecture stays a separate `.so` file.

New file `modules/linux.py`:

- `run_task_build_pdfium()` — calls `pdfium.get_pdfium_by_target("linux")`.
- `run_task_patch()` — applies `patch.apply_shared_library("linux")` and `patch.apply_public_headers("linux")` (converts `component("pdfium")` to `shared_library("pdfium")` in `BUILD.gn`, and removes the `COMPONENT_BUILD` guard around `FPDF_EXPORT` so symbols are always exported). Does **not** apply the `BUILDCONFIG.gn` visibility patch that Android's `run_task_patch` applies — that patch specifically restores hidden Android JNI symbols and doesn't apply to Linux.
- `run_task_build()` — for each configuration/target, `gn gen` + `ninja -C ... pdfium -v`, same loop shape as `android.py`/`macos.py`.
- `run_task_install()` — copies each architecture's `.so` into `build/linux/<config>/lib/<arch>/`, fixes header include paths, copies public headers. Same shape as Android's install step (per-arch subdirectories, no merge).
- `run_task_test()` — runs `file` on each installed `.so` to confirm it's a valid ELF binary for the expected architecture, same as `android.py`. No CMake sample execution (the existing `sample/` CMake project is macOS-specific via CoreGraphics/Foundation/Security frameworks; building a Linux-specific sample that actually renders a PDF is out of scope for this pass — the `file` check is what Android already considers sufficient).
- `run_task_archive()` — tars up `build/linux/<config>/` into `linux.tgz`, same shape as the other platforms.

## Config changes (`modules/config.py`)

```python
# linux
configurations_linux = ["release"]
shared_lib_linux = True
targets_linux = [
    {"target_os": "linux", "target_cpu": "x64", "pdfium_os": "linux"},
    {"target_os": "linux", "target_cpu": "arm64", "pdfium_os": "linux"},
]
```

## Build args (`modules/common.py`)

`get_build_args` already has a dormant `elif target_os == "linux":` branch (present in the codebase but never wired up to any module/config/workflow — a leftover from upstream). Extend it with the portability flags from Approach A:

```python
elif target_os == "linux":
    args.append("clang_use_chrome_plugins=false")
    args.append("pdf_is_standalone=true")
    args.append("pdf_bundle_freetype=true")
    # + static libstdc++/libgcc linking flags (exact gn args TBD during implementation)
```

## `make.py`

Add the same six task entries as the other platforms: `build-pdfium-linux`, `patch-linux`, `build-linux`, `install-linux`, `test-linux`, `archive-linux`, wired to the new `modules/linux.py` functions, following the existing `elif task == "..."` pattern.

## CI workflow (`.github/workflows/linux.yml`)

Mirrors `android.yml`: native `ubuntu-24.04` runner, no Docker, no emulation. Cross-compiling arm64 from an x64 host is compile-only (no execution needed until a consumer runs the binary), and `run_task_test`'s `file` check doesn't execute the binary either, so no QEMU/emulation step is needed in CI.

Same job shape as the other three workflows: checkout → Python setup → CMake/Ninja setup → PDFium checkout → patch → patch-check → build → install → test → archive → upload artifact, plus the existing tag-triggered `deploy` job pattern for release uploads.

## Local development (OrbStack)

Add a section to `docs/BUILD_LINUX.md` (parallel to `BUILD_ANDROID.md`'s "Docker (macOS arm64)" section) documenting OrbStack as the recommended way for macOS users to get a real Linux machine locally, replacing the role Docker plays for Android/WASM:

- Create a VM matching the pinned build-baseline image chosen for Approach A (so local builds are tested against the same glibc floor as CI produces), e.g. `orb create ubuntu:<pinned-version>`.
- Run the same commands from the "How to compile" + `BUILD_LINUX.md` steps inside the VM — no code changes needed since OrbStack provides an actual Ubuntu environment.
- This is local-only tooling; the CI workflow is unaffected and continues to run natively on the GitHub-hosted `ubuntu-24.04` runner.

## Documentation (`docs/BUILD_LINUX.md`)

Same structure as `BUILD_ANDROID.md`: prerequisite steps link, PDFium checkout, patch, build, install, test steps, plus the OrbStack section described above. Update `README.md` to move "Linux" from the roadmap list into the supported-platforms checklist and add a workflow badge, matching the existing pattern for other platforms.

## Deferred to implementation (not guessed here)

- **Exact pinned base image/glibc version for Approach A** — needs research into what's both old enough for broad compatibility and still supported by the Chromium/depot_tools toolchain requirements.
- **Exact arm64 sysroot mechanism** for cross-compiling from an x64 host — Chromium's `build/linux/sysroot_scripts/install-sysroot.py`, or something triggered automatically via `gclient sync` with `target_os=['linux']`. To be confirmed while implementing `run_task_build_pdfium`/`run_task_build`, not assumed here.
- **Exact static-linking gn args** (`-static-libstdc++ -static-libgcc` equivalents in GN/ninja args) — to be worked out against PDFium's actual `BUILD.gn`/toolchain files during implementation.

## Risks

- If the pinned old-glibc baseline conflicts with a minimum toolchain version required by the pinned PDFium `chromium/7623` branch, Approach A may need a newer floor than initially hoped — this is a real possibility to validate early in implementation rather than late.
- Bundling FreeType (rather than dynamically linking system FreeType) increases binary size per architecture; not expected to be a problem for a server/app consumer but worth noting.
