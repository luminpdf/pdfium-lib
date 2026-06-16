import os
import platform
import subprocess

from pygemstones.io import file as f
from pygemstones.system import runner as r
from pygemstones.util import log as l

import modules.config as c


# -----------------------------------------------------------------------------
def _depot_tools_dir():
    return os.path.abspath(os.path.join(os.getcwd(), "build", "depot-tools"))


def _depot_tools_usable(tools_dir):
    gn_bin = os.path.join(tools_dir, "gn")
    if not os.path.isfile(gn_bin):
        return False

    marker = os.path.join(tools_dir, "python3_bin_reldir.txt")
    if os.path.isfile(marker):
        with open(marker, encoding="utf-8") as handle:
            reldir = handle.read().strip()
        python_bin = os.path.join(tools_dir, reldir, "python3", "bin", "python3")
        if os.path.isfile(python_bin):
            try:
                subprocess.run(
                    [python_bin, "-c", "import sys"],
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                return False

    try:
        subprocess.run(
            [gn_bin, "--version"],
            capture_output=True,
            check=True,
            timeout=15,
        )
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _depot_tools_bootstrapped(tools_dir):
    gclient_bin = os.path.join(tools_dir, "gclient")
    bootstrap_marker = os.path.join(tools_dir, "python3_bin_reldir.txt")
    return os.path.isfile(gclient_bin) and os.path.isfile(bootstrap_marker)


def _bootstrap_depot_tools(tools_dir):
    ensure_bootstrap = os.path.join(tools_dir, "ensure_bootstrap")
    if not os.path.isfile(ensure_bootstrap):
        return
    l.colored("Bootstrapping depot_tools...", l.YELLOW)
    env = os.environ.copy()
    env["DEPOT_TOOLS_UPDATE"] = "1"
    subprocess.run(
        [ensure_bootstrap],
        cwd=tools_dir,
        env=env,
        check=False,
        timeout=180,
    )


def _ninja_runs(path):
    if not path or not os.path.isfile(path):
        return False
    try:
        subprocess.run(
            [path, "--version"],
            capture_output=True,
            check=True,
            timeout=15,
        )
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _binary_description(path):
    try:
        result = subprocess.run(
            ["file", "-bL", path],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def _gn_runs(path):
    if not path or not os.path.isfile(path):
        return False
    try:
        subprocess.run(
            [path, "--version"],
            capture_output=True,
            check=True,
            timeout=15,
        )
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def resolve_gn_command():
    """Return a runnable gn binary (full path), bypassing depot_tools lookup."""
    override = os.environ.get("PDFIUM_GN", "").strip()
    if override and _gn_runs(override):
        return [override]

    if os.environ.get("PDFIUM_DOCKER_BUILD") == "1":
        docker_gn = "/opt/pdfium-buildtools/linux64/gn"
        if _gn_runs(docker_gn):
            return [docker_gn]

    for bin_dir in os.environ.get("PATH", "").split(os.pathsep):
        bin_dir = bin_dir.rstrip(os.sep)
        if not bin_dir or os.path.basename(bin_dir) == "depot_tools":
            continue
        candidate = os.path.join(bin_dir, "gn")
        if _gn_runs(candidate):
            return [candidate]

    system = platform.system()
    if system == "Darwin":
        buildtools_subdir = "mac"
    elif system == "Linux":
        buildtools_subdir = "linux64"
    else:
        buildtools_subdir = None

    if buildtools_subdir:
        source_dir = os.environ.get("PDFIUM_SOURCE_DIR", "")
        if source_dir:
            buildtools_dir = os.path.join(source_dir, "buildtools", buildtools_subdir)
            for candidate in (
                os.path.join(buildtools_dir, "gn", "gn"),
                os.path.join(buildtools_dir, "gn"),
            ):
                if _gn_runs(candidate):
                    return [candidate]

    raise RuntimeError(
        "No runnable gn binary found. Set PDFIUM_GN or restore buildtools/linux64."
    )


def resolve_ninja_command():
    """Return a runnable ninja binary, bypassing depot_tools' third_party lookup."""
    override = os.environ.get("PDFIUM_NINJA", "").strip()
    if override and _ninja_runs(override):
        return [override]

    for bin_dir in os.environ.get("PATH", "").split(os.pathsep):
        bin_dir = bin_dir.rstrip(os.sep)
        if not bin_dir or os.path.basename(bin_dir) == "depot_tools":
            continue
        candidate = os.path.join(bin_dir, "ninja")
        if _ninja_runs(candidate):
            return [candidate]

    system = platform.system()
    if system == "Darwin":
        buildtools_dir = os.path.join("buildtools", "mac")
    elif system == "Linux":
        buildtools_dir = os.path.join("buildtools", "linux64")
    else:
        buildtools_dir = None

    if buildtools_dir:
        source_dir = os.environ.get("PDFIUM_SOURCE_DIR", "")
        if source_dir:
            candidate = os.path.join(source_dir, buildtools_dir, "ninja")
            if _ninja_runs(candidate):
                return [candidate]

    raise RuntimeError(
        "No runnable ninja binary found. Install ninja-build or set PDFIUM_NINJA."
    )


def prepend_pdfium_buildtools(source_dir):
    """Prefer pdfium's pinned gn/ninja over depot_tools wrappers."""
    if os.environ.get("PDFIUM_DOCKER_BUILD") == "1":
        buildtools_dir = "/opt/pdfium-buildtools/linux64"
    else:
        system = platform.system()
        if system == "Darwin":
            buildtools_dir = os.path.join(source_dir, "buildtools", "mac")
        elif system == "Linux":
            buildtools_dir = os.path.join(source_dir, "buildtools", "linux64")
        else:
            return

    gn_paths = [
        os.path.join(buildtools_dir, "gn", "gn"),
        os.path.join(buildtools_dir, "gn"),
    ]
    gn_bin = next((p for p in gn_paths if os.path.isfile(p)), None)
    if not gn_bin:
        return

    gn_dir = os.path.dirname(gn_bin)
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if gn_dir not in path_entries:
        os.environ["PATH"] = gn_dir + os.pathsep + os.environ.get("PATH", "")


def ensure_depot_tools_on_path():
    """Clone depot_tools if needed and prepend to PATH (gclient, gn, ninja)."""
    if os.environ.get("PDFIUM_DOCKER_BUILD") == "1":
        os.environ["DEPOT_TOOLS_UPDATE"] = "0"
        os.environ["DEPOT_TOOLS_WIN_TOOLCHAIN"] = "0"
        return

    tools_dir = _depot_tools_dir()
    gclient_bin = os.path.join(tools_dir, "gclient")

    if os.path.isfile(gclient_bin) and _depot_tools_usable(tools_dir):
        pass
    elif not os.path.isfile(gclient_bin):
        l.colored("depot_tools missing; cloning into build/depot-tools...", l.YELLOW)
        build_dir = os.path.join(os.getcwd(), "build")
        f.create_dir(build_dir)
        r.run(
            [
                "git",
                "clone",
                "https://chromium.googlesource.com/chromium/tools/depot_tools.git",
                "depot-tools",
            ],
            cwd=build_dir,
        )
        if not _depot_tools_bootstrapped(tools_dir):
            _bootstrap_depot_tools(tools_dir)
    else:
        l.colored(
            "Skipping build/depot-tools (not runnable on this host); using PATH",
            l.YELLOW,
        )
        tools_dir = None

    os.environ["DEPOT_TOOLS_UPDATE"] = "0"
    os.environ["DEPOT_TOOLS_WIN_TOOLCHAIN"] = "0"

    if tools_dir and _depot_tools_usable(tools_dir):
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        if tools_dir not in path_entries:
            os.environ["PATH"] = tools_dir + os.pathsep + os.environ.get("PATH", "")


# -----------------------------------------------------------------------------
def run_task_build_depot_tools():
    l.colored("Building depot tools...", l.YELLOW)

    build_dir = os.path.join("build")
    f.create_dir(build_dir)

    tools_dir = os.path.join(build_dir, "depot-tools")
    f.remove_dir(tools_dir)

    cwd = build_dir
    command = [
        "git",
        "clone",
        "https://chromium.googlesource.com/chromium/tools/depot_tools.git",
        "depot-tools",
    ]
    r.run(command, cwd=cwd)

    _bootstrap_depot_tools(tools_dir)

    l.colored("Execute on your terminal:", l.PURPLE)
    l.m("export PATH=$PATH:$PWD/build/depot-tools")

    os.environ["DEPOT_TOOLS_UPDATE"] = "0"
    os.environ["DEPOT_TOOLS_WIN_TOOLCHAIN"] = "0"

    l.ok()


# -----------------------------------------------------------------------------
def run_task_build_emsdk():
    l.colored("Building Emscripten SDK...", l.YELLOW)

    build_dir = os.path.join("build")
    f.create_dir(build_dir)

    tools_dir = os.path.join(build_dir, "emsdk")
    f.remove_dir(tools_dir)

    cwd = build_dir
    command = [
        "git",
        "clone",
        "https://github.com/emscripten-core/emsdk.git",
    ]
    r.run(command, cwd=cwd)

    cwd = tools_dir
    command = " ".join(["./emsdk", "install", c.emsdk_version])
    r.run(command, cwd=cwd, shell=True)

    cwd = tools_dir
    command = " ".join(["./emsdk", "activate", c.emsdk_version])
    r.run(command, cwd=cwd, shell=True)

    cwd = tools_dir
    command = " ".join(["source", "emsdk_env.sh"])
    r.run(command, cwd=cwd, shell=True)

    l.colored(
        "Execute on your terminal the following file according to your system:",
        l.PURPLE,
    )
    l.m("File: emsdk_env")
    l.m("Directory: " + cwd)

    l.ok()


# -----------------------------------------------------------------------------
def run_task_format():
    # check
    try:
        subprocess.check_output(["black", "--version"])
    except OSError:
        l.e("Black is not installed, check: https://github.com/psf/black")

    # start
    l.colored("Formating files...", l.YELLOW)

    # make.py
    command = [
        "black",
        "make.py",
    ]
    r.run(command)

    # modules
    command = [
        "black",
        "modules/",
    ]
    r.run(command)

    l.ok()


# -----------------------------------------------------------------------------
def get_build_args(
    config,
    shared,
    target_os,
    target_cpu,
    target_environment=None,
    libc=None,
    enable_v8=False,
):
    args = []

    arg_is_debug = "true" if config == "debug" else "false"

    args.append(f"is_debug={arg_is_debug}")
    args.append("pdf_use_partition_alloc=false")
    args.append(f'target_cpu="{target_cpu}"')
    args.append(f'target_os="{target_os}"')
    args.append(f"pdf_enable_v8={str(enable_v8).lower()}")
    args.append(f"pdf_enable_xfa={str(enable_v8).lower()}")
    args.append("treat_warnings_as_errors=false")
    args.append("is_component_build=false")

    if config == "release":
        args.append("symbol_level=0")

    if enable_v8:
        args.append("v8_use_external_startup_data=false")
        args.append("v8_enable_i18n_support=false")

    if target_os == "android":
        args.append("clang_use_chrome_plugins=false")
        args.append("default_min_sdk_version=23")
        args.append("pdf_is_standalone=true")
        args.append("pdf_bundle_freetype=true")
    elif target_os == "ios":
        args.append("ios_enable_code_signing=false")
        args.append("use_blink=true")
        args.append("pdf_is_standalone=true")
        args.append('target_environment="{0}"'.format(target_environment))
        args.append('ios_deployment_target="12.0"')

        if enable_v8 and target_cpu == "arm64":
            args.append('arm_control_flow_integrity="none"')
        args.append("clang_use_chrome_plugins=false")

        # static lib
        if not shared:
            args.append("pdf_is_complete_lib=true")
    elif target_os == "linux":
        args.append("clang_use_chrome_plugins=false")
        args.append("pdf_is_standalone=true")
    elif target_os.startswith("mac"):
        args.append('mac_deployment_target="11.0.0"')
        args.append("clang_use_chrome_plugins=false")
        args.append("pdf_is_standalone=true")
        args.append("use_custom_libcxx=false")
        args.append("use_sysroot=false")
        args.append("use_allocator_shim=false")

        # static lib
        if not shared:
            args.append("pdf_is_complete_lib=true")
    elif target_os.startswith("emscripten"):
        args.append("pdf_is_complete_lib=true")
        args.append("is_clang=false")
        args.append("use_custom_libcxx=false")

    if libc == "musl":
        args.append("is_musl=true")
        args.append("is_clang=false")
        args.append("use_custom_libcxx=false")

        if enable_v8:
            if target_cpu == "arm":
                args.append(
                    'v8_snapshot_toolchain="//build/toolchain/linux:clang_x86_v8_arm"'
                )
            elif target_cpu == "arm64":
                args.append(
                    'v8_snapshot_toolchain="//build/toolchain/linux:clang_x64_v8_arm64"'
                )
            else:
                args.append(
                    f'v8_snapshot_toolchain="//build/toolchain/linux:{target_cpu}"'
                )

    return args
