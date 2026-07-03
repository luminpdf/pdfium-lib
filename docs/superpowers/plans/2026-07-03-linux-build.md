# Linux PDFium Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Linux target (`x64` + `arm64`, shared `.so`) to this project's build pipeline, following the same `make.py` task pattern already used for iOS/macOS/Android/WASM.

**Architecture:** New `modules/linux.py` mirrors `modules/android.py` (both are shared-library, multi-arch targets with no fat-binary merge step), driven by new `configurations_linux`/`shared_lib_linux`/`targets_linux` entries in `modules/config.py` and an extended `elif target_os == "linux":` branch in `modules/common.py`'s `get_build_args`. Portability across Linux distros comes from Chromium's own `use_sysroot`/`use_custom_libcxx` defaults for `target_os="linux"` (both `true`), not from a custom base image — the only extra work needed is explicitly fetching the Chromium Linux sysroot for each target arch, since this repo's PDFium checkout doesn't declare `target_cpu` to gclient (only `target_os`), so the automatic sysroot-fetch hook is not expected to trigger.

**Tech Stack:** Python 3 (`make.py` / `modules/*.py`, using the existing `pygemstones` helpers), GN + Ninja (PDFium's own build system), depot_tools/gclient (PDFium checkout), GitHub Actions (CI).

## Global Constraints

- PDFium branch is pinned to `chromium/7623` (`modules/config.py: pdfium_git_branch`) — do not change it as part of this work.
- No V8/XFA support — do not pass `enable_v8=True` anywhere for the Linux target, matching every other platform's default.
- No `docker/linux/Dockerfile` — out of scope per the design spec (`docs/superpowers/specs/2026-07-03-linux-build-design.md`); local dev/testing uses the existing OrbStack VM instead.
- Build/patch/install/test/archive steps that involve actually running `gclient`/`gn`/`ninja` cannot be run on this machine directly (it's macOS) — they must be run inside the OrbStack Linux VM named `my-build-vm` (Ubuntu 22.04 jammy, arm64), reachable via `orb run -m my-build-vm bash -c "<command>"`, with this repo visible inside the VM at `/mnt/mac/Users/dangminhhoanglong/emdash/worktrees/pdfium-lib/emdash/linux-build-iqgr7`.
- **Do not build directly on the `/mnt/mac/...` path.** It's a virtiofs mount from macOS; PDFium's checkout is hundreds of thousands of small files, and building across that mount is dramatically slower than the VM's native disk. Every VM-side task below clones/copies the repo into `~/linux-build` inside the VM first, and copies only the finished `build/linux/` output (and any modified source files) back out through the mount.
- Every task that changes a tracked file ends with a `git commit`, run from this macOS checkout (not from inside the VM).

---

### Task 1: Add Linux configuration and build args

**Files:**
- Modify: `modules/config.py`
- Modify: `modules/common.py:156-158`

**Interfaces:**
- Produces: `c.configurations_linux` (`list[str]`), `c.shared_lib_linux` (`bool`), `c.targets_linux` (`list[dict]` with keys `target_os`, `target_cpu`, `pdfium_os`, `sysroot_arch`) — consumed by Task 2's `modules/linux.py`.
- Produces: `cm.get_build_args(..., target_os="linux", ...)` now also appending `pdf_bundle_freetype=true`.

This task is pure Python and has no dependency on the VM — it can be verified with a plain `python3` import check.

- [ ] **Step 1: Add the Linux section to `modules/config.py`**

Open `modules/config.py` and add this block after the `wasm` section at the end of the file:

```python

# linux
configurations_linux = ["release"]
shared_lib_linux = True
targets_linux = [
    {
        "target_os": "linux",
        "target_cpu": "x64",
        "pdfium_os": "linux",
        "sysroot_arch": "amd64",
    },
    {
        "target_os": "linux",
        "target_cpu": "arm64",
        "pdfium_os": "linux",
        "sysroot_arch": "arm64",
    },
]
```

(`sysroot_arch` uses Chromium's `install-sysroot.py --arch=` naming, which differs from GN's `target_cpu` naming: `amd64` instead of `x64`, but `arm64` matches.)

- [ ] **Step 2: Verify the config parses**

Run: `python3 -c "import modules.config as c; print(c.targets_linux); print(c.shared_lib_linux); print(c.configurations_linux)"`
Expected: prints the list of two target dicts, `True`, and `['release']`, with no traceback.

- [ ] **Step 3: Extend the `linux` branch in `modules/common.py`**

In `modules/common.py`, find the existing dormant branch (around line 156):

```python
    elif target_os == "linux":
        args.append("clang_use_chrome_plugins=false")
        args.append("pdf_is_standalone=true")
```

Change it to:

```python
    elif target_os == "linux":
        args.append("clang_use_chrome_plugins=false")
        args.append("pdf_is_standalone=true")
        args.append("pdf_bundle_freetype=true")
```

Do **not** add `use_sysroot=` or `use_custom_libcxx=` lines — leaving them unset keeps Chromium's `true` defaults for `target_os="linux"`, which is the actual portability mechanism (see the design spec's "Targets and portability approach" section).

- [ ] **Step 4: Verify the build args**

Run: `python3 -c "import modules.common as cm; print(cm.get_build_args('release', True, 'linux', 'x64'))"`
Expected: a Python list containing `'clang_use_chrome_plugins=false'`, `'pdf_is_standalone=true'`, and `'pdf_bundle_freetype=true'`, with no `use_sysroot` or `use_custom_libcxx` entries.

- [ ] **Step 5: Commit**

```bash
git add modules/config.py modules/common.py
git commit -m "Add Linux target configuration and build args"
```

---

### Task 2: Create `modules/linux.py` and wire it into `make.py`

**Files:**
- Create: `modules/linux.py`
- Modify: `make.py`

**Interfaces:**
- Consumes: `c.configurations_linux`, `c.shared_lib_linux`, `c.targets_linux` from Task 1; `cm.get_build_args` from Task 1; `patch.apply_shared_library(target)` and `patch.apply_public_headers(target)` from `modules/patch.py` (already exist, used identically by `modules/android.py`); `p.get_pdfium_by_target(target)` from `modules/pdfium.py` (already exists).
- Produces: `linux.run_task_build_pdfium()`, `linux.run_task_patch()`, `linux.run_task_build()`, `linux.run_task_install()`, `linux.run_task_test()`, `linux.run_task_archive()` — consumed by `make.py`'s task dispatch and by Tasks 3-6 below (which run these via `python3 make.py <task>-linux`).

This task is also pure Python (no VM execution needed yet — the functions will fail if invoked without a real PDFium checkout, which is expected; Tasks 3-6 are where they're actually run against the VM).

- [ ] **Step 1: Create `modules/linux.py`**

```python
import os
import tarfile

from pygemstones.io import file as f
from pygemstones.system import runner as r
from pygemstones.util import log as l

import modules.common as cm
import modules.config as c
import modules.patch as patch
import modules.pdfium as p


# -----------------------------------------------------------------------------
def run_task_build_pdfium():
    p.get_pdfium_by_target("linux")

    l.colored("Installing Linux sysroots...", l.YELLOW)

    pdfium_dir = os.path.join("build", "linux", "pdfium")

    for target in c.targets_linux:
        r.run(
            [
                "python3",
                "build/linux/sysroot_scripts/install-sysroot.py",
                "--arch={0}".format(target["sysroot_arch"]),
            ],
            cwd=pdfium_dir,
        )

    l.ok()


# -----------------------------------------------------------------------------
def run_task_patch():
    l.colored("Patching files...", l.YELLOW)

    # shared lib
    if c.shared_lib_linux:
        patch.apply_shared_library("linux")

    # public headers
    if c.shared_lib_linux:
        patch.apply_public_headers("linux")

    l.ok()


# -----------------------------------------------------------------------------
def run_task_build():
    l.colored("Building libraries...", l.YELLOW)

    current_dir = f.current_dir()

    # configs
    for config in c.configurations_linux:
        # targets
        for target in c.targets_linux:
            main_dir = os.path.join(
                "build",
                target["target_os"],
                "pdfium",
                "out",
                "{0}-{1}-{2}".format(target["target_os"], target["target_cpu"], config),
            )

            f.recreate_dir(main_dir)

            os.chdir(
                os.path.join(
                    "build",
                    target["target_os"],
                    "pdfium",
                )
            )

            # generating files...
            l.colored(
                'Generating files to arch "{0}" and configuration "{1}"...'.format(
                    target["target_cpu"], config
                ),
                l.YELLOW,
            )

            args = cm.get_build_args(
                config,
                c.shared_lib_linux,
                target["pdfium_os"],
                target["target_cpu"],
            )

            args_str = " ".join(args)

            command = [
                "gn",
                "gen",
                "out/{0}-{1}-{2}".format(
                    target["target_os"], target["target_cpu"], config
                ),
                "--args='{0}'".format(args_str),
            ]
            r.run(" ".join(command), shell=True)

            # compiling...
            l.colored(
                'Compiling to arch "{0}" and configuration "{1}"...'.format(
                    target["target_cpu"], config
                ),
                l.YELLOW,
            )

            command = [
                "ninja",
                "-C",
                "out/{0}-{1}-{2}".format(
                    target["target_os"], target["target_cpu"], config
                ),
                "pdfium",
                "-v",
            ]
            r.run(command)

            os.chdir(current_dir)

    l.ok()


# -----------------------------------------------------------------------------
def run_task_install():
    l.colored("Installing libraries...", l.YELLOW)

    # configs
    for config in c.configurations_linux:
        f.recreate_dir(os.path.join("build", "linux", config))

        # targets
        for target in c.targets_linux:
            out_dir = "{0}-{1}-{2}".format(
                target["target_os"], target["target_cpu"], config
            )

            source_lib_dir = os.path.join("build", "linux", "pdfium", "out", out_dir)

            lib_dir = os.path.join("build", "linux", config, "lib")
            target_dir = os.path.join(lib_dir, target["target_cpu"])

            f.recreate_dir(target_dir)

            for basename in os.listdir(source_lib_dir):
                if basename.endswith(".so"):
                    pathname = os.path.join(source_lib_dir, basename)

                    if os.path.isfile(pathname):
                        f.copy_file(pathname, os.path.join(target_dir, basename))

            # fix include path
            source_include_path = os.path.join(
                "build",
                target["target_os"],
                "pdfium",
                "public",
            )

            headers = f.find_files(source_include_path, "*.h", True)

            for header in headers:
                f.replace_in_file(header, '#include "public/', '#include "../')

        # headers
        l.colored("Copying header files...", l.YELLOW)

        include_dir = os.path.join("build", "linux", "pdfium", "public")
        include_cpp_dir = os.path.join(include_dir, "cpp")
        target_include_dir = os.path.join("build", "linux", config, "include")
        target_include_cpp_dir = os.path.join(target_include_dir, "cpp")

        f.recreate_dir(target_include_dir)
        f.copy_files(include_dir, target_include_dir, "*.h")
        f.copy_files(include_cpp_dir, target_include_cpp_dir, "*.h")

    l.ok()


# -----------------------------------------------------------------------------
def run_task_test():
    l.colored("Testing...", l.YELLOW)

    for config in c.configurations_linux:
        for target in c.targets_linux:
            lib_dir = os.path.join(
                "build", "linux", config, "lib", target["target_cpu"]
            )

            command = ["file", os.path.join(lib_dir, "libpdfium.cr.so")]
            r.run(command)

    l.ok()


# -----------------------------------------------------------------------------
def run_task_archive():
    l.colored("Archiving...", l.YELLOW)

    current_dir = os.getcwd()
    lib_dir = os.path.join(current_dir, "build", "linux")
    output_filename = os.path.join(current_dir, "linux.tgz")

    tar = tarfile.open(output_filename, "w:gz")

    for configuration in c.configurations_linux:
        tar.add(
            name=os.path.join(lib_dir, configuration),
            arcname=os.path.basename(os.path.join(lib_dir, configuration)),
            filter=lambda x: (
                None
                if "_" in x.name
                and not x.name.endswith(".h")
                and not x.name.endswith(".so")
                and os.path.isfile(x.name)
                else x
            ),
        )

    tar.close()

    l.ok()
```

- [ ] **Step 2: Wire the tasks into `make.py`**

Add the import near the top of `make.py`, alphabetically among the existing `import modules.*` lines:

```python
import modules.ios as ios
import modules.linux as linux
import modules.macos as macos
```

Add a new `#######################\n# Linux\n#######################` section to `make.py`, placed after the `Android` section and before the `WASM` section, mirroring the Android block exactly:

```python
    #######################
    # Linux
    #######################

    # build pdfium - linux
    elif task == "build-pdfium-linux":
        linux.run_task_build_pdfium()

    # patch - linux
    elif task == "patch-linux":
        linux.run_task_patch()

    # build - linux
    elif task == "build-linux":
        linux.run_task_build()

    # install - linux
    elif task == "install-linux":
        linux.run_task_install()

    # test - linux
    elif task == "test-linux":
        linux.run_task_test()

    # archive - linux
    elif task == "archive-linux":
        linux.run_task_archive()

```

Also add the six new task names to the module docstring's `Tasks:` list at the top of `make.py`, in a new block after the Android tasks and before the WASM tasks:

```
  - build-pdfium-linux
  - patch-linux
  - build-linux
  - install-linux
  - test-linux
  - archive-linux
```

- [ ] **Step 3: Verify the wiring**

Run: `python3 -c "import make"`
Expected: no traceback (confirms the new import and module reference are syntactically valid).

Run: `python3 make.py -h`
Expected: help text prints, including the six new `*-linux` task names in the usage docstring, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add modules/linux.py make.py
git commit -m "Add Linux build module and wire it into make.py"
```

---

### Task 3: Bootstrap the OrbStack VM and check out PDFium for the Linux target

**Files:** none (environment setup + a real PDFium checkout inside the VM; no repo files change in this task).

**Interfaces:**
- Produces: a working copy of this repo at `~/linux-build` inside `my-build-vm`, with `build/depot-tools` and `build/linux/pdfium` populated — consumed by Task 4 (arm64 build spike) and Task 5 (x64 build spike), which run inside that same VM checkout.

This is the first task that actually exercises the VM. Its job is to validate the checkout mechanics (Task 1/2's code assumes `p.get_pdfium_by_target` and the sysroot script both work as expected) before Task 4 attempts a real compile.

- [ ] **Step 1: Copy the repo into the VM's native filesystem**

Run (from this macOS checkout):

```bash
orb run -m my-build-vm bash -c "rm -rf ~/linux-build && cp -r /mnt/mac/Users/dangminhhoanglong/emdash/worktrees/pdfium-lib/emdash/linux-build-iqgr7 ~/linux-build"
```

Expected: exits 0. This copies the current state of the repo (including Tasks 1-2's changes, once committed) into the VM's own disk.

- [ ] **Step 2: Install system packages needed by depot_tools/gclient/pip**

Run:

```bash
orb run -m my-build-vm bash -c "sudo apt-get update && sudo apt-get install -y python3-pip lsb-release"
```

Expected: exits 0 (packages already present is fine — `git`, `ninja-build`, `cmake` were already confirmed present on this VM).

- [ ] **Step 3: Install Python requirements**

Run:

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && python3 -m pip install -r requirements.txt --user"
```

Expected: exits 0, installs `docopt`, `black`, `pygemstones`, `wasmtime` without error.

- [ ] **Step 4: Fetch depot_tools**

Run:

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && python3 make.py build-depot-tools"
```

Expected: exits 0; `~/linux-build/build/depot-tools` exists afterward. Verify with:

```bash
orb run -m my-build-vm bash -c "test -d ~/linux-build/build/depot-tools/gclient && echo FOUND"
```
Expected output: `FOUND`.

- [ ] **Step 5: Run the Linux PDFium checkout (Task 2's `run_task_build_pdfium`)**

Run:

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && export PATH=\$PATH:\$PWD/build/depot-tools && python3 make.py build-pdfium-linux"
```

This will take a while (PDFium + its third-party deps, shallow-cloned, plus two `install-sysroot.py` invocations). Let it run to completion rather than interrupting it.

Expected: exits 0. If `install-sysroot.py` fails with a "file not found" style error for the script path, run:

```bash
orb run -m my-build-vm bash -c "find ~/linux-build/build/linux/pdfium/build -iname 'install-sysroot.py'"
```

and update the path used in `modules/linux.py`'s `run_task_build_pdfium` (in this macOS checkout) to whatever path this reveals, then re-copy the repo into the VM (Step 1) and re-run this step.

- [ ] **Step 6: Verify the checkout and sysroots landed**

Run:

```bash
orb run -m my-build-vm bash -c "test -f ~/linux-build/build/linux/pdfium/BUILD.gn && echo CHECKOUT_OK && ls ~/linux-build/build/linux/pdfium/build/linux/ | grep -i sysroot"
```

Expected: prints `CHECKOUT_OK` followed by at least one directory name containing `sysroot` (confirms both the checkout and at least one sysroot are present; if only one arch's sysroot directory appears, note which one in the commit message for Task 4/5 to investigate).

- [ ] **Step 7: Commit**

No repo files changed in this task (it's pure environment validation), so there is nothing to commit. If Step 5 required a path fix, that fix was already committed as part of re-doing Task 2's Step 4 commit — amend that instead of creating an empty commit here:

```bash
git status
```
Expected: if `modules/linux.py` shows as modified due to a path fix, commit it now:
```bash
git add modules/linux.py
git commit -m "Fix install-sysroot.py path discovered during VM checkout spike"
```
If nothing changed, skip committing for this task.

---

### Task 4: arm64 build spike (native compile on the VM)

**Files:** none expected, unless Step 4 reveals a required code change (see below).

**Interfaces:**
- Consumes: the VM checkout from Task 3, `linux.run_task_patch()` and `linux.run_task_build()` from Task 2.
- Produces: a working `libpdfium.cr.so` for `arm64` in `~/linux-build/build/linux/pdfium/out/linux-arm64-release/`, confirming the build-args/patch logic from Tasks 1-2 actually compiles — this is the precondition Task 5 (x64) and Task 6 (install/test/archive) build on.

The VM (`my-build-vm`) is itself `aarch64`, so `arm64` is the *native* target here — building it first isolates "does the patch + build-args pipeline work at all" from "does cross-compilation work," which is the next task's concern.

- [ ] **Step 1: Run the patch task**

Run:

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && python3 make.py patch-linux"
```

Expected: exits 0. Verify the patch applied:

```bash
orb run -m my-build-vm bash -c "grep -c 'shared_library(\"pdfium\")' ~/linux-build/build/linux/pdfium/BUILD.gn"
```
Expected output: `1` (or greater).

- [ ] **Step 2: Write a throwaway single-arch spike script**

Rather than editing `modules/config.py` in place (fragile to patch and revert correctly), write a standalone script that reuses `modules/linux.py`'s real build logic but overrides the target list in memory for this one run. Create this file directly inside the VM checkout (it is a throwaway spike file, never copied into this macOS repo or committed):

```bash
orb run -m my-build-vm bash -c "cat > ~/linux-build/spike_build_one_arch.py << 'PYEOF'
import sys

import modules.config as c
import modules.linux as linux

arch = sys.argv[1]

c.targets_linux = [t for t in c.targets_linux if t[\"target_cpu\"] == arch]

if not c.targets_linux:
    raise SystemExit(f\"No target found for arch {arch}\")

linux.run_task_build()
PYEOF"
```

- [ ] **Step 3: Run the build for arm64 only**

Run:

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && export PATH=\$PATH:\$PWD/build/depot-tools && python3 spike_build_one_arch.py arm64"
```

Expected: exits 0. If `gn gen` fails with an error mentioning a missing sysroot (message will reference `use_sysroot` or a path under `build/linux/*-sysroot`), that means the sysroot fetched in Task 3 Step 5 didn't cover this arch/naming — re-run `install-sysroot.py --arch=arm64` manually inside `~/linux-build/build/linux/pdfium` and retry before concluding this step failed.

- [ ] **Step 4: Verify the output binary**

Run:

```bash
orb run -m my-build-vm bash -c "file ~/linux-build/build/linux/pdfium/out/linux-arm64-release/libpdfium.cr.so"
```

Expected: output contains `ELF 64-bit`, `ARM aarch64`, and `shared object`. If the filename isn't `libpdfium.cr.so` (e.g. it's plain `libpdfium.so`), list the directory instead:

```bash
orb run -m my-build-vm bash -c "ls ~/linux-build/build/linux/pdfium/out/linux-arm64-release/*.so"
```

and update the filename used in `modules/linux.py`'s `run_task_test` (in this macOS checkout) to match, then commit that fix.

Note: `modules/config.py` itself was never modified by this task (Step 2's spike script filters the target list in memory, not on disk), so Task 5 can proceed directly against the same VM checkout with both targets intact.

- [ ] **Step 5: Commit (only if Step 4 required a filename fix)**

```bash
git status
```
If `modules/linux.py` shows changes, commit:
```bash
git add modules/linux.py
git commit -m "Fix shared library output filename discovered during arm64 build spike"
```
Otherwise skip — this task made no permanent code changes.

---

### Task 5: x64 build spike (cross-compile on the VM)

**Files:** none expected, unless a fix is required (same pattern as Task 4).

**Interfaces:**
- Consumes: the VM checkout (now with both targets restored) and `linux.run_task_build()` from Task 2.
- Produces: a working `libpdfium.cr.so` for `x64` in `~/linux-build/build/linux/pdfium/out/linux-x64-release/`, confirming cross-compilation (the direction CI will actually need, since GitHub's `ubuntu-24.04` runners are x64 and `arm64` is the cross target there — the reverse of this VM).

- [ ] **Step 1: Build both targets**

Task 4 validated arm64 alone via the throwaway spike script; `modules/config.py` in the VM checkout still has both targets (it was never modified), so running the real `build-linux` task now exercises both arches, including x64:

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && export PATH=\$PATH:\$PWD/build/depot-tools && python3 make.py build-linux"
```

Expected: exits 0, and takes noticeably longer than Task 4 (now building two archs). If `gn gen` for the `x64` target fails on a missing sysroot, run `install-sysroot.py --arch=amd64` manually inside `~/linux-build/build/linux/pdfium` (this is the case the design spec flagged as likely needed regardless of host arch) and retry.

- [ ] **Step 2: Verify the x64 output binary**

Run:

```bash
orb run -m my-build-vm bash -c "file ~/linux-build/build/linux/pdfium/out/linux-x64-release/libpdfium.cr.so"
```

Expected: output contains `ELF 64-bit`, `x86-64`, and `shared object`.

- [ ] **Step 3: Commit (only if a fix was required)**

```bash
git status
```
Commit any change to `modules/linux.py` or `modules/common.py` the same way as prior tasks, with a message describing what the x64 cross-compile spike revealed. Otherwise skip.

---

### Task 6: Install, test, and archive — full end-to-end run

**Files:** none expected to change (this validates Task 2's `run_task_install`/`run_task_test`/`run_task_archive` against the real builds from Tasks 4-5).

**Interfaces:**
- Consumes: the compiled output from Task 5 (both arches present under `~/linux-build/build/linux/pdfium/out/`).
- Produces: `~/linux-build/build/linux/release/lib/{x64,arm64}/libpdfium.cr.so`, `~/linux-build/build/linux/release/include/`, and `~/linux-build/linux.tgz` — the final artifact shape Task 7's CI workflow will upload.

- [ ] **Step 1: Run install**

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && python3 make.py install-linux"
```

Expected: exits 0. Verify:

```bash
orb run -m my-build-vm bash -c "ls ~/linux-build/build/linux/release/lib/x64/ ~/linux-build/build/linux/release/lib/arm64/ ~/linux-build/build/linux/release/include/"
```

Expected: each `lib/<arch>/` directory contains a `.so` file, and `include/` contains PDFium's public headers (e.g. `fpdfview.h`).

- [ ] **Step 2: Run test**

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && python3 make.py test-linux"
```

Expected: exits 0, prints two `file` command results (one per arch), each reporting a valid ELF shared object matching the arch (`aarch64` for arm64, `x86-64` for x64). If this step fails because the installed filename doesn't match `libpdfium.cr.so`, apply the same filename fix as Task 4 Step 4 to `run_task_install`'s copy logic isn't at fault (it copies anything ending in `.so`, so this should only be a `run_task_test` filename mismatch, not an install bug).

- [ ] **Step 3: Run archive**

```bash
orb run -m my-build-vm bash -c "cd ~/linux-build && python3 make.py archive-linux"
```

Expected: exits 0, creates `~/linux-build/linux.tgz`. Verify:

```bash
orb run -m my-build-vm bash -c "tar -tzf ~/linux-build/linux.tgz | head -20"
```

Expected: lists `release/lib/x64/...`, `release/lib/arm64/...`, and `release/include/...` entries.

- [ ] **Step 4: Copy the artifact back for inspection (optional but recommended)**

```bash
orb run -m my-build-vm bash -c "cp ~/linux-build/linux.tgz /mnt/mac/Users/dangminhhoanglong/emdash/worktrees/pdfium-lib/emdash/linux-build-iqgr7/linux.tgz"
```

This lets you inspect the real artifact from macOS. Delete it afterward (it's a build output, not a tracked file):

```bash
rm -f linux.tgz
```

- [ ] **Step 5: Commit (only if a fix was required in Step 2)**

Same pattern as prior tasks — commit only if `modules/linux.py` changed.

---

### Task 7: Add the CI workflow

**Files:**
- Create: `.github/workflows/linux.yml`

**Interfaces:**
- Consumes: the six `make.py *-linux` tasks from Task 2 (now validated end-to-end by Tasks 3-6).

This mirrors `.github/workflows/android.yml`'s structure (native `ubuntu-24.04` runner, no Docker), dropping the Android-specific NDK setup step and adding a PDFium build-dependencies step (the Linux-target equivalent of Android's `install-build-deps-android.sh`, confirmed to exist as `install-build-deps.sh` in Task 3's checkout).

- [ ] **Step 1: Create `.github/workflows/linux.yml`**

```yaml
name: Linux

on:
  push:
    paths-ignore:
      - '**.md'
      - 'docs/**'
      - 'extras/images/**'

jobs:
  build:
    name: ${{ matrix.config.name }}
    runs-on: ${{ matrix.config.os }}
    strategy:
      fail-fast: false
      matrix:
        config:
          - { name: "Ubuntu", os: "ubuntu-24.04", target: "linux" }

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Upgrade PIP
        run: python3 -m pip install --upgrade pip setuptools wheel

      - name: Install CMake
        uses: jwlawson/actions-setup-cmake@v2
        with:
          cmake-version: "3.24.0"

      - name: Install Ninja
        uses: seanmiddleditch/gha-setup-ninja@master
        with:
          version: "1.12.1"

      - name: Verify
        run: |
          python3 --version
          cmake --version
          ninja --version

      - name: Python requirements
        run: python3 -m pip install -r requirements.txt --user

      - name: Depot tools
        run: python3 make.py build-depot-tools

      - name: Environment
        run: echo "$PWD/build/depot-tools" >> $GITHUB_PATH

      - name: PDFium
        run: python3 make.py build-pdfium-${{ matrix.config.target }}

      - name: PDFium build dependencies
        run: |
          cd build/${{ matrix.config.target }}/pdfium
          echo n | ./build/install-build-deps.sh || true

      - name: Patch
        run: python3 make.py patch-${{ matrix.config.target }}

      - name: Patch - Check
        run: python3 make.py patch-${{ matrix.config.target }}

      - name: Build
        run: python3 make.py build-${{ matrix.config.target }}

      - name: Install
        run: python3 make.py install-${{ matrix.config.target }}

      - name: Test
        run: python3 make.py test-${{ matrix.config.target }}

      - name: Archive
        run: python3 make.py archive-${{ matrix.config.target }}

      - name: Save
        uses: actions/upload-artifact@v4
        with:
          name: artifact-${{ matrix.config.target }}
          path: ${{ matrix.config.target }}.tgz

  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    needs: [build]
    if: startsWith(github.ref, 'refs/tags/')
    steps:
      - name: Load
        uses: actions/download-artifact@v4
        with:
          name: artifact-linux
      - name: Get release
        id: get_release
        uses: bruceadams/get-release@v1.2.2
        env:
          GITHUB_TOKEN: ${{ github.token }}
      - name: Upload release asset
        id: upload-release-asset
        uses: actions/upload-release-asset@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          upload_url: ${{ steps.get_release.outputs.upload_url }}
          asset_path: linux.tgz
          asset_name: linux.tgz
          asset_content_type: application/tar+gzip
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/linux.yml'))"`
Expected: no traceback (requires `pyyaml`; if not installed, run `python3 -m pip install pyyaml --user` first — this is a one-off local check, not a new project dependency).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/linux.yml
git commit -m "Add Linux CI workflow"
```

Note: this commit is not pushed as part of this plan — pushing/triggering CI is a separate, explicit decision for the user to make (see plan completion notes).

---

### Task 8: Documentation

**Files:**
- Create: `docs/BUILD_LINUX.md`
- Modify: `README.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Create `docs/BUILD_LINUX.md`**

```markdown
# Build for Linux

1. First, execute all steps in the [How to compile](https://github.com/paulocoutinhox/pdfium-lib/tree/master?tab=readme-ov-file#how-to-compile) section

2. Get PDFium:
```python3 make.py build-pdfium-linux```

3. PDFium Linux dependencies:
```
cd build/linux/pdfium
echo n | ./build/install-build-deps.sh
cd ../../..
```

4. Patch:
```python3 make.py patch-linux```

5. Compile:
```python3 make.py build-linux```

6. Install libraries:
```python3 make.py install-linux```

7. Test:
```python3 make.py test-linux```

Obs:
- The file **make.py** need be executed with python version 3.
- You need run all steps in a Linux machine (real, vm or docker) to it works.

## OrbStack (macOS)

If you're on macOS, [OrbStack](https://orbstack.dev/) gives you a real Linux VM to run these steps without Docker:

1. Create a VM: `orb create ubuntu`
2. Open a shell in it: `orb shell`
3. `cd` to this repo through the automatic macOS mount, e.g. `cd /mnt/mac/Users/<you>/path/to/pdfium-lib`
4. Run the steps above from inside that shell.

Obs: for anything beyond a quick check, copy this repo into the VM's own filesystem (e.g. `~/pdfium-lib`) instead of working directly on the `/mnt/mac/...` mount — PDFium's checkout has hundreds of thousands of small files, and building across that mount is significantly slower than building on the VM's native disk. Copy the `build/linux/<config>/` output back out through the mount when you're done.
```

- [ ] **Step 2: Update `README.md`'s badge block**

In `README.md`, find the badges block (lines 9-14) and add a Linux badge after the Android one, before WASM:

```
  <a href="https://github.com/paulocoutinhox/pdfium-lib/actions/workflows/android.yml"><img src="https://github.com/paulocoutinhox/pdfium-lib/actions/workflows/android.yml/badge.svg" alt="PDFium - Android"></a>
  <a href="https://github.com/paulocoutinhox/pdfium-lib/actions/workflows/linux.yml"><img src="https://github.com/paulocoutinhox/pdfium-lib/actions/workflows/linux.yml/badge.svg" alt="PDFium - Linux"></a>
  <a href="https://github.com/paulocoutinhox/pdfium-lib/actions/workflows/wasm.yml"><img src="https://github.com/paulocoutinhox/pdfium-lib/actions/workflows/wasm.yml/badge.svg" alt="PDFium - WASM"></a>
```

(Matches the existing badges' URL convention, which all point at `paulocoutinhox/pdfium-lib` rather than this fork's own remote — consistent with every other existing badge, not something to fix as part of this change.)

- [ ] **Step 3: Update the `## Platforms` section**

Change:

```markdown
- [x] iOS device (arm64)
- [x] iOS simulator (x86_64, arm64)
- [X] Android (armv7, armv8, x86, x86_64)
- [x] macOS (x86_64, arm64)
- [x] WASM (Web Assembly)

Platforms in roadmap:

- Linux
- Windows
```

to:

```markdown
- [x] iOS device (arm64)
- [x] iOS simulator (x86_64, arm64)
- [X] Android (armv7, armv8, x86, x86_64)
- [x] macOS (x86_64, arm64)
- [x] Linux (x64, arm64)
- [x] WASM (Web Assembly)

Platforms in roadmap:

- Windows
```

- [ ] **Step 4: Add a "How to compile for Linux" section**

After the existing `## How to compile for Android` section and before `## How to compile for WASM`, add:

```markdown
## How to compile for Linux

Check tutorial here: [Build for Linux](docs/BUILD_LINUX.md)

```

- [ ] **Step 5: Commit**

```bash
git add docs/BUILD_LINUX.md README.md
git commit -m "Add Linux build documentation"
```

---

## Plan completion notes

- This plan does not push any commits or trigger CI — that's a separate decision. Once all tasks pass, review the commits with `git log` and decide whether to push the branch / open a PR.
- The `my-build-vm` OrbStack VM used throughout Tasks 3-6 is a pre-existing local dev machine, not something this plan creates or tears down. Leftover state in `~/linux-build` inside that VM is safe to leave in place or delete (`orb run -m my-build-vm rm -rf ~/linux-build`) once the plan is done — it isn't referenced by anything outside this plan's execution.
