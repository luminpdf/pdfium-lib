# Linux Build for PDFium — Design

## Goal

Add a Linux target to this project's build pipeline, producing a shared library (`libpdfium.so`) for x64 and arm64, for use as a native library in a Linux app/server. This closes one of the two items on the README roadmap ("Linux, Windows").

## Non-goals

- Windows build (separate roadmap item, not part of this design).
- V8/XFA (forms) support — no existing platform enables it by default; Linux follows the same default.
- A `docker/linux/Dockerfile` for CI — no existing workflow (iOS, macOS, Android, WASM) runs its build inside Docker in CI; the `docker/android` and `docker/wasm` images exist purely as local-dev convenience. Local dev/testing for Linux will use an OrbStack Linux VM instead (see below), so no Dockerfile is needed for this project.

## Targets and portability approach

Targets: `x64` and `arm64`, matching the macOS target list shape (two architectures, no more).

**Portability approach: Approach A — portable build, via Chromium's Linux GN defaults (not a custom base image).**

Because the resulting `.so` is meant to be linked into a consumer's Linux app or server whose OS/distro isn't controlled by this project, we need to avoid it requiring a newer glibc/libstdc++ than the CI runner happens to have.

Research during plan-writing (see plan doc) found this is already handled by Chromium/PDFium's own defaults for `target_os="linux"`, so **no custom base image and no manual static-link flags are needed**:

- `use_sysroot` defaults to `true` for `target_os="linux"`, which links against Chromium's bundled old-Debian sysroot instead of the build machine's glibc — this is the actual portability mechanism, not the choice of CI base image.
- `use_custom_libcxx` defaults to `true` for Linux, which statically links Chromium's own libc++ instead of depending on the consumer's libstdc++ version.
- Bundle FreeType into the library (`pdf_bundle_freetype=true`, matching how the Android target already avoids depending on the host's system FreeType/fontconfig).

Net result: build straight on the CI runner's default Ubuntu image (no pinned old base image required) — the sysroot and custom-libc++ defaults already produce a `.so` per architecture that doesn't depend on the build machine's own toolchain/glibc versions. The one piece that does need explicit handling is fetching the **arm64** sysroot when cross-compiling from an x64 host, since this repo's PDFium checkout only declares `target_os` (not `target_cpu`) to gclient — see the implementation plan for the exact command.

This was chosen as the default without an explicit user confirmation (the clarifying question went unanswered) because it directly matches the stated use case (an app/server whose deployment environment isn't specified) and is the safer default to build around.

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
```

No `use_sysroot`/`use_custom_libcxx` overrides are added — leaving them unset keeps Chromium's Linux defaults (both `true`), which is what provides the portability described above.

## `make.py`

Add the same six task entries as the other platforms: `build-pdfium-linux`, `patch-linux`, `build-linux`, `install-linux`, `test-linux`, `archive-linux`, wired to the new `modules/linux.py` functions, following the existing `elif task == "..."` pattern.

## CI workflow (`.github/workflows/linux.yml`)

Mirrors `android.yml`: native `ubuntu-24.04` runner, no Docker, no emulation. Cross-compiling arm64 from an x64 host is compile-only (no execution needed until a consumer runs the binary), and `run_task_test`'s `file` check doesn't execute the binary either, so no QEMU/emulation step is needed in CI.

Same job shape as the other three workflows: checkout → Python setup → CMake/Ninja setup → PDFium checkout → patch → patch-check → build → install → test → archive → upload artifact, plus the existing tag-triggered `deploy` job pattern for release uploads.

## Local development (OrbStack)

Add a section to `docs/BUILD_LINUX.md` (parallel to `BUILD_ANDROID.md`'s "Docker (macOS arm64)" section) documenting OrbStack as the recommended way for macOS users to get a real Linux machine locally, replacing the role Docker plays for Android/WASM:

- Create a default Ubuntu VM (matching the CI runner's Ubuntu version is convenient but not load-bearing for portability, since the sysroot/custom-libc++ defaults — not the build machine's own OS version — are what make the artifact portable): `orb create ubuntu`.
- Run the same commands from the "How to compile" + `BUILD_LINUX.md` steps inside the VM — no code changes needed since OrbStack provides an actual Ubuntu environment.
- This is local-only tooling; the CI workflow is unaffected and continues to run natively on the GitHub-hosted `ubuntu-24.04` runner.

## Documentation (`docs/BUILD_LINUX.md`)

Same structure as `BUILD_ANDROID.md`: prerequisite steps link, PDFium checkout, patch, build, install, test steps, plus the OrbStack section described above. Update `README.md` to move "Linux" from the roadmap list into the supported-platforms checklist and add a workflow badge, matching the existing pattern for other platforms.

## Deferred to implementation (not guessed here)

- **arm64 sysroot fetch mechanism** — `get_pdfium_by_target` only appends `target_os` (not `target_cpu`) to the `.gclient` file, so the automatic gclient hook that fetches Chromium's Linux sysroots (conditioned on `checkout_arm64`-style vars) is unlikely to fetch the arm64 sysroot on an x64 host. The implementation plan verifies this empirically and, if needed, calls `build/linux/sysroot_scripts/install-sysroot.py --arch=arm64` explicitly. Whether the x64/amd64 sysroot needs the same explicit treatment is also verified empirically rather than assumed.

## Risks

- Bundling FreeType (rather than dynamically linking system FreeType) increases binary size per architecture; not expected to be a problem for a server/app consumer but worth noting.
- This design's build-arg reasoning (`use_sysroot`/`use_custom_libcxx` defaults) is based on Chromium's documented general Linux build behavior, not a build actually run against this repo's pinned `chromium/7623` PDFium branch — the implementation plan's first task is a real end-to-end build spike specifically to confirm this before the rest of the module is built out on top of it.
