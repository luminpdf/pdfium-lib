# Building PDFium for Windows from the Lumin Fork

This guide explains how to build a native Windows `pdfium.dll` (x64) from the
Lumin PDFium fork. The DLL exports the fork's `LMP_*` extension functions
alongside the standard `FPDF*` API and is intended to be consumed by a native
Rust app through the `pdfium-render` crate's runtime dynamic loading
(`Pdfium::bind_to_library`).

The Windows build **clones** the fork directly with `gclient` (no local-copy
step). It pulls `git@github.com:luminpdf/pdfium.git` at branch `luminpdf/main`
(configured by `pdfium_win_git_url` / `pdfium_win_git_branch` in
`modules/config.py`). **SSH access to that fork repository is required** for the
clone to succeed.

## Why x64 only

`FPDF_CALLCONV` is `__stdcall`. The `pdfium-render` bindings are declared
`extern "C"`, whose calling convention matches `__stdcall` only on x64. On x86
the conventions differ and symbol resolution / calls would be wrong. The build
config therefore targets x64 exclusively (`targets_windows` in
`modules/config.py`).

## The export patch (the whole point)

`pdfium/public/fpdfview.h` only makes `FPDF_EXPORT` resolve to
`__declspec(dllexport)` inside `#if defined(COMPONENT_BUILD)`. A non-component
DLL would export ZERO symbols, and `Pdfium::bind_to_library` — which resolves
every `LMP_*` / `FPDF*` function by string name via `libloading` — would fail.

Two pieces fix this, both wired into the Windows build:

1. **`patch-windows`** runs `patch.apply_public_headers("win")`, which
   strips the `COMPONENT_BUILD` guard from `public/fpdfview.h`. After the patch,
   on WIN32 `FPDF_EXPORT` becomes:

   ```c
   #if defined(FPDF_IMPLEMENTATION)
   #define FPDF_EXPORT __declspec(dllexport)
   #else
   #define FPDF_EXPORT __declspec(dllimport)
   #endif
   ```

2. **`build-windows`** defines `FPDF_IMPLEMENTATION` for the DLL's own
   translation units. PDFium's `BUILD.gn` only defines it via the
   `pdfium_implementation_config`, attached to the `pdfium_public_headers`
   *group* — not to the `pdfium` target that the shared-library patch produces.
   So `modules/common.py` `get_build_args()` appends
   `extra_cflags="/DFPDF_IMPLEMENTATION"` for `target_os == "win"`, forcing the
   `dllexport` branch.

`patch-windows` also runs `patch.apply_shared_library("win")`, which renames
`component("pdfium")` to `shared_library("pdfium")` so ninja produces a DLL.

## Prerequisites

- Windows 10/11 x64
- **Long-path support enabled** (see below — this is MANDATORY, not optional)
- **Visual Studio Build Tools 2022** (or full Visual Studio 2022) with the
  "Desktop development with C++" workload (MSVC v143 / `VC.Tools.x86.x64`), a
  **Windows 10/11 SDK**, and the **Debugging Tools for Windows** SDK feature
  (see the `dbghelp.dll` note below)
- **Python 3** (the real interpreter — NOT the Microsoft Store `python` alias)
  with pip
- `depot_tools` installed at a **short** path (see below)
- **SSH access to `git@github.com:luminpdf/pdfium.git`** (the build clones the
  fork at branch `luminpdf/main`); confirm `ssh -T git@github.com` succeeds

> `DEPOT_TOOLS_WIN_TOOLCHAIN=0` is already exported by
> `modules/common.py` (`run_task_build_depot_tools`). This tells depot_tools to
> use your locally installed Visual Studio / Windows SDK instead of Google's
> internal toolchain. Because of this, you must also set the VS toolchain
> env vars yourself — see "Visual Studio toolchain environment variables" below.

### Enable long-path support (MANDATORY, one-time, requires admin)

Windows' legacy `MAX_PATH` limit (260 characters) breaks **two** stages of this
build:

1. The depot_tools **CIPD bootstrap** (which deploys a bundled cpython3 with very
   deep internal paths).
2. The Chromium `gclient sync` and the build itself, which create deeply nested
   directory trees that overflow 260 chars.

Enable long paths once from an **elevated** PowerShell (no reboot needed):

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```

Verify it took effect:

```powershell
(Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem").LongPathsEnabled
# should print: 1
```

### Install Python dependencies

```powershell
cd packages\wasm\pdfium-lib
pip3 install -r requirements.txt
```

### Install depot_tools at a SHORT path (first time only)

Even with long paths enabled, install depot_tools at a **short base path** (e.g.
`C:\dt` or `C:\Users\<you>\dt`), NOT deep under the repo. The CIPD bootstrap's
bundled cpython3 has very deep internal paths that fail to deploy under a long
base path — you will see errors like "Access is denied" or "lost a race when
renaming".

The `build-depot-tools` make task clones into `build/depot-tools` (already deep,
under `packages/wasm/pdfium-lib/`). **On Windows, prefer cloning manually to a
short path and putting THAT on PATH** instead:

```powershell
git clone --depth 1 https://chromium.googlesource.com/chromium/tools/depot_tools.git C:\dt
$env:PATH = "C:\dt;$env:PATH"
```

If you already have a working short-path checkout, just put it on PATH:

```powershell
$env:PATH = "C:\dt;$env:PATH"
```

### Visual Studio toolchain environment variables (REQUIRED)

With `DEPOT_TOOLS_WIN_TOOLCHAIN=0`, Chromium's `build/vs_toolchain.py` does NOT
reliably auto-detect VS Build Tools 2022, and `gn gen` fails with **"No supported
Visual Studio can be found."** Set these before building (adjust the paths to your
actual install — VS Build Tools 2022 is typically under
`C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools`):

```powershell
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = "0"
$env:vs2022_install = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
$env:GYP_MSVS_OVERRIDE_PATH = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
$env:GYP_MSVS_VERSION = "2022"
```

**`vs2022_install` is the primary override** that the newer Chromium base
(`luminpdf/main`) actually honors. Its `build/vs_toolchain.py`
`DetectVisualStudioPath` checks a `vs<year>_install` env var (e.g.
`vs2022_install`) and otherwise falls back to hardcoded `%ProgramFiles%` paths.
A real build against this base proved that `GYP_MSVS_OVERRIDE_PATH` alone was
**not** sufficient and still failed with "No supported Visual Studio can be
found." Set `vs2022_install` to your actual VS Build Tools 2022 install path.
Note our install lives under `Program Files (x86)`, while the base's hardcoded
fallback for 2022 looks under `Program Files` — which is exactly why the explicit
`vs2022_install` var is required. Keep `GYP_MSVS_OVERRIDE_PATH` /
`GYP_MSVS_VERSION` as well; they are harmless and are read by some steps.

Required VS components: **"Desktop development with C++"** (MSVC v143 /
`VC.Tools.x86.x64`) AND a **Windows 10/11 SDK**.

### "Debugging Tools for Windows" (`dbghelp.dll`) requirement

`vs_toolchain.py`'s `_CopyDebugger` step requires
`<WindowsSdkDir>\Debuggers\x64\dbghelp.dll` (this is non-optional in the script)
and will otherwise raise:

> dbghelp.dll not found ... You must install ... the 'Debugging Tools for
> Windows' feature.

You have two options:

- **Proper fix:** install the **"Debugging Tools for Windows"** feature of the
  Windows SDK (via the Windows SDK installer / "Add or Remove Programs" → modify
  the SDK).
- **No-admin workaround** (if you can't modify the SDK install under
  `Program Files`): redirect the SDK to a **writable shadow directory** via the
  `WINDOWSSDKDIR` env var. Create a directory whose entries are
  **directory junctions** to the real `Windows Kits\10` subfolders (`Include`,
  `Lib`, `bin`, `Redist`, etc.) PLUS a **real** `Debuggers\x64` folder containing
  `dbghelp.dll` and `dbgcore.dll` (both already exist in `C:\Windows\System32`).
  Then set `WINDOWSSDKDIR` to that shadow directory —
  `vs_toolchain.py`'s `SetEnvironmentAndGetSDKDir()` honors it. The System32
  copies of `dbghelp.dll` / `dbgcore.dll` are adequate for building `pdfium.dll`:
  they're only used by Chrome for crash symbolization, not by our build output.

> Run the commands from a shell where the VS environment is initialized (e.g. a
> **x64 Native Tools Command Prompt for VS 2022**, or PowerShell after the env
> vars above are set) so MSVC, `cl.exe`, and the Windows SDK are on PATH.

## Build pipeline

1. `build-pdfium-windows` — Clone the PDFium fork + sync Chromium deps via gclient
2. `patch-windows` — Apply shared-library + public-header (dllexport) patches
3. `build-windows` — Compile with gn + ninja (x64, release)
4. `install-windows` — Copy DLL + import library + headers into `build/win/release/`
5. `archive-windows` — Package `build/win/` into `win.tgz`

## Step 1: Clone PDFium and sync dependencies

This clones the Lumin PDFium fork (`git@github.com:luminpdf/pdfium.git` at branch
`luminpdf/main`) into `build/win/pdfium/` using `gclient config` + `gclient sync`,
then downloads Chromium build dependencies. The gclient `target_os` is set to
`win`. **SSH access to the fork repo is required.**

```powershell
cd packages\wasm\pdfium-lib
$env:PATH = "C:\dt;$env:PATH"
python make.py build-pdfium-windows
```

**Known issue:** If this fails with an authentication / "Permission denied
(publickey)" error, your SSH key is not authorized for the fork. Confirm
`ssh -T git@github.com` reports your username and that you have access to
`luminpdf/pdfium`.

## Step 2: Patch

```powershell
python make.py patch-windows
```

Applies:
- shared library (`component("pdfium")` -> `shared_library("pdfium")`)
- public headers (strips the `COMPONENT_BUILD` guard so `dllexport` is active)

## Step 3: Build

Compiles the `pdfium` shared library for x64 (release) using gn + ninja.

```powershell
python make.py build-windows
```

## Step 4: Install

Copies the DLL, its import library, and the public headers into
`build/win/release/`. No `lipo` (single x64 arch).

```powershell
python make.py install-windows
```

## Step 5: Archive (optional)

```powershell
python make.py archive-windows
```

Produces `win.tgz` at the `pdfium-lib` root.

## Verify outputs

After a successful build, outputs are in `build\win\release\`:

| Output | Description |
|--------|-------------|
| `build\win\release\lib\pdfium.dll` | Runtime DLL (x64) exporting `FPDF*` + `LMP_*` |
| `build\win\release\lib\pdfium.dll.lib` | Import library (for compile-time linking, if desired) |
| `build\win\release\lib\pdfium.dll.pdb` | Debug symbols (if produced) |
| `build\win\release\include\` | Public C API headers |
| `build\win\release\include\cpp\` | C++ wrapper headers |

Confirm the DLL exports symbols by name (sanity check before wiring up Rust):

```powershell
dumpbin /exports build\win\release\lib\pdfium.dll | findstr FPDF_InitLibrary
dumpbin /exports build\win\release\lib\pdfium.dll | findstr LMP_
```

Expected results from a successful build:

- The total export count is roughly **546 symbols**.
- `FPDF_InitLibrary` is present (the first `findstr` prints a match).
- `dumpbin /exports pdfium.dll | findstr LMP_` lists the **~40 `LMP_*`** fork
  extension functions.

To see the total count quickly:

```powershell
dumpbin /exports build\win\release\lib\pdfium.dll | findstr /R "^ *[0-9]" | Measure-Object -Line
```

If `dumpbin /exports` lists no `FPDF*` symbols, the dllexport patch or the
`FPDF_IMPLEMENTATION` define did not take effect — re-check Step 2 and the
`extra_cflags` arg in `modules/common.py`.

## Consuming the DLL from Rust

The native Rust app loads the DLL at runtime via `pdfium-render`:

```rust
use pdfium_render::prelude::*;

let bindings = Pdfium::bind_to_library(
    Pdfium::pdfium_platform_library_name_at_path("./"), // resolves "pdfium.dll"
)?;
let pdfium = Pdfium::new(bindings);
```

`bind_to_library` resolves each `FPDF*` / `LMP_*` function by string name, which
is exactly why the dllexport patch + `FPDF_IMPLEMENTATION` define are mandatory.

## Verified build sequence (full build)

This is the exact, known-good sequence used to produce a working `pdfium.dll`
(exporting ~546 symbols including ~40 `LMP_*` functions). It assumes long paths are
already enabled and depot_tools is checked out at a short path (`C:\dt`).

```powershell
cd packages\wasm\pdfium-lib

# depot_tools (short path) on PATH — NOT build\depot-tools
$env:PATH = "C:\dt;$env:PATH"

# VS toolchain env (with DEPOT_TOOLS_WIN_TOOLCHAIN=0, these are required;
# vs2022_install is the primary override the luminpdf/main Chromium base reads)
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = "0"
$env:vs2022_install = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
$env:GYP_MSVS_OVERRIDE_PATH = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
$env:GYP_MSVS_VERSION = "2022"

# Only if using the no-admin Debugging Tools shadow (see Prerequisites):
# $env:WINDOWSSDKDIR = "C:\sdk-shadow"

# Build pipeline (use real Python 3, NOT the Microsoft Store `python` alias)
python make.py build-pdfium-windows; `
python make.py patch-windows; `
python make.py build-windows; `
python make.py install-windows
```

## Troubleshooting

### `gn` or `ninja` not found

Ensure depot_tools is on PATH (use the short-path checkout, not
`build\depot-tools`):

```powershell
$env:PATH = "C:\dt;$env:PATH"
```

### CIPD bootstrap fails: "Access is denied" / "lost a race when renaming"

depot_tools is installed at too deep a path. Re-clone it to a short base path
(e.g. `C:\dt`) and confirm long-path support is enabled — see the
"Enable long-path support" and "Install depot_tools at a SHORT path" sections.

### `gn gen` fails: "No supported Visual Studio can be found."

With `DEPOT_TOOLS_WIN_TOOLCHAIN=0`, `vs_toolchain.py` does not auto-detect VS
Build Tools 2022. Set `vs2022_install` (the primary override the `luminpdf/main`
Chromium base's `DetectVisualStudioPath` reads), plus `GYP_MSVS_OVERRIDE_PATH`
and `GYP_MSVS_VERSION` — see "Visual Studio toolchain environment variables" in
Prerequisites. `GYP_MSVS_OVERRIDE_PATH` alone is NOT sufficient on this base when
VS Build Tools 2022 lives under `Program Files (x86)`.

### Build fails: "dbghelp.dll not found ... 'Debugging Tools for Windows'"

`vs_toolchain.py`'s `_CopyDebugger` requires `dbghelp.dll` in the SDK's
`Debuggers\x64`. Install the "Debugging Tools for Windows" SDK feature, or use
the `WINDOWSSDKDIR` shadow-directory workaround — see the `dbghelp.dll`
note in Prerequisites.

### Long paths / `MAX_PATH` errors during `gclient sync` or build

Long-path support is not enabled. Enable it from an elevated PowerShell and
verify — see "Enable long-path support" in Prerequisites.

### Inspecting or overriding the gn build args

The Windows build does **not** pass `--args` on the gn command line. Unlike a
POSIX shell, `cmd.exe` does not strip the single quotes in `--args='...'`, so
gn would receive a literal quote and error. Instead, `modules/windows.py`
`run_task_build` writes the args to `out/<target_os>-<target_cpu>-<config>/args.gn`
(one arg per line) and runs `gn gen <out-dir>` with no `--args`; gn reads
`args.gn` from the out dir automatically.

To inspect or override the args, edit that file directly, for example:

```powershell
notepad build\win\pdfium\out\win-x64-release\args.gn
```

then re-run `gn gen` (or `python make.py build-windows`, which regenerates the
file from `modules/common.py` `get_build_args()` on every run).

### DLL builds but exports zero symbols

- Confirm `patch-windows` reported "Applied: public headers" (not "Skipped").
- Confirm `is_component_build=false` is present (it is, unconditionally) AND
  that `extra_cflags="/DFPDF_IMPLEMENTATION"` appears in the gn args for `win`.
- Re-run `dumpbin /exports` to verify.

### Build fails: toolchain not found

Set the VS environment first (use the **x64 Native Tools Command Prompt for
VS 2022**, or PowerShell with the env vars set) and ensure
`DEPOT_TOOLS_WIN_TOOLCHAIN=0`, `vs2022_install`, `GYP_MSVS_OVERRIDE_PATH`, and
`GYP_MSVS_VERSION` are set — see "Visual Studio toolchain environment variables"
in Prerequisites.
