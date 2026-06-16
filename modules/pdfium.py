import os
import platform
import re
import shutil
import subprocess

from pygemstones.io import file as f
from pygemstones.system import runner as r
from pygemstones.util import log as l

import modules.common as cm
import modules.config as c
import modules.pdfium_paths as paths


# -----------------------------------------------------------------------------
def get_pdfium_shared(enable_v8=False):
    """Sync DEPS into the local pdfium-lib/pdfium/ checkout (shared by iOS and Android)."""
    l.colored("Building PDFium (shared mobile source)...", l.YELLOW)
    cm.ensure_depot_tools_on_path()

    root_pdfium = os.path.abspath(
        paths.resolve_pdfium_source_dir() or paths.DEFAULT_ROOT_PDFIUM
    )
    if not os.path.isdir(os.path.dirname(root_pdfium)):
        os.makedirs(os.path.dirname(root_pdfium), exist_ok=True)

    if not _is_git_checkout(root_pdfium):
        l.e(
            f"PDFium source at {root_pdfium} is not a git checkout. "
            "Run: git submodule update --init --recursive pdfium-lib"
        )

    paths.cleanup_legacy_platform_build_dirs()

    build_dir = paths.gclient_build_dir()
    f.create_dir(build_dir)
    _clean_stale_shared_checkout(build_dir, root_pdfium)
    _link_gclient_pdfium_slot(build_dir, root_pdfium)

    l.colored(f"Using PDFium source at {root_pdfium}", l.YELLOW)

    # gclient checks out into <gclient-root>/pdfium; the symlink sends DEPS into root_pdfium/.
    _configure_shared_gclient(build_dir, enable_v8)

    _clean_pdfium_deps_before_sync(root_pdfium)

    l.colored("Syncing DEPS for local PDFium source...", l.YELLOW)
    r.run(
        [
            "gclient",
            "sync",
            "--no-history",
            "--shallow",
        ],
        cwd=build_dir,
    )

    _reset_pdfium_subtrees(root_pdfium)

    if not os.path.isfile(os.path.join(root_pdfium, "BUILD.gn")):
        l.e(
            f"PDFium source missing BUILD.gn at {root_pdfium}. "
            "Run: git submodule update --init --recursive pdfium-lib"
        )

    l.ok()


# -----------------------------------------------------------------------------
def ensure_android_shared_deps():
    """Fetch Android-only DEPS when the tree was synced for iOS on macOS."""
    if platform.system() == "Linux":
        ensure_linux_buildtools()
        ensure_linux_host_toolchain()
        ensure_android_toolchain()

    root_pdfium = os.path.abspath(
        paths.resolve_pdfium_source_dir() or paths.DEFAULT_ROOT_PDFIUM
    )
    if _android_deps_ready(root_pdfium):
        return

    l.colored(
        "Android DEPS missing (NDK toolchain and/or LLVM runtimes); "
        "syncing gclient (adding target_os android)...",
        l.YELLOW,
    )
    l.colored(
        "gclient sync can take several minutes (longer on Docker bind mounts).",
        l.YELLOW,
    )
    cm.ensure_depot_tools_on_path()

    build_dir = paths.gclient_build_dir()
    f.create_dir(build_dir)
    _link_gclient_pdfium_slot(build_dir, root_pdfium)
    _ensure_gclient_has_android(build_dir)
    _clean_pdfium_deps_before_sync(root_pdfium)

    _run_gclient_sync(build_dir)

    if not _android_deps_ready(root_pdfium):
        l.e(
            "Android DEPS still missing after gclient sync. "
            "Run: pnpm pdfium-init-android (or python3 make.py build-pdfium-shared in Docker)"
        )

    l.colored("Android DEPS sync complete.", l.GREEN)


# -----------------------------------------------------------------------------
def ensure_android_toolchain():
    """Ensure third_party/android_toolchain NDK exists (not fetched by iOS-only sync)."""
    if platform.system() != "Linux":
        return

    root_pdfium = os.path.abspath(
        paths.resolve_pdfium_source_dir() or paths.DEFAULT_ROOT_PDFIUM
    )
    if _android_toolchain_ready(root_pdfium):
        return

    l.colored(
        "Android NDK toolchain missing under pdfium/third_party/android_toolchain "
        "(common after an iOS build on macOS). Restoring...",
        l.YELLOW,
    )

    if not _restore_docker_android_toolchain(root_pdfium):
        return

    l.colored("Android NDK toolchain ready.", l.GREEN)


# -----------------------------------------------------------------------------
def ensure_linux_buildtools():
    """Ensure buildtools/linux64/gn exists (iOS sync on Mac only fetches buildtools/mac)."""
    if platform.system() != "Linux":
        return

    root_pdfium = os.path.abspath(
        paths.resolve_pdfium_source_dir() or paths.DEFAULT_ROOT_PDFIUM
    )
    if _linux_buildtools_ready(root_pdfium):
        return

    l.colored(
        "Linux buildtools missing under pdfium/buildtools/linux64 "
        "(common after an iOS build on macOS). Restoring...",
        l.YELLOW,
    )

    if not _restore_docker_buildtools(root_pdfium):
        l.e(
            "Linux buildtools still missing.\n"
            "  Fix: PDFIUM_FORCE_DOCKER_BUILD=1 pnpm pdfium-build-android"
        )

    l.colored("Linux buildtools ready.", l.GREEN)


# -----------------------------------------------------------------------------
def ensure_linux_host_toolchain():
    """Ensure third_party/llvm-build clang is Linux ELF (not macOS from bind mount)."""
    if platform.system() != "Linux":
        return

    root_pdfium = os.path.abspath(
        paths.resolve_pdfium_source_dir() or paths.DEFAULT_ROOT_PDFIUM
    )
    if _linux_host_toolchain_ready(root_pdfium):
        return

    clang_path = _llvm_clang_path(root_pdfium)
    if os.path.isfile(clang_path):
        description = _clang_binary_description(clang_path)
    else:
        description = "(missing)"

    l.colored(
        "Wrong or missing Linux Chromium clang at {} ({}). "
        "This often happens when pdfium/ was synced on macOS for iOS. "
        "Re-syncing DEPS for Android...".format(clang_path, description),
        l.YELLOW,
    )

    if not _restore_docker_llvm_cache(root_pdfium):
        llvm_build = os.path.join(root_pdfium, "third_party", "llvm-build")
        if os.path.isdir(llvm_build):
            f.remove_dir(llvm_build)

        cm.ensure_depot_tools_on_path()

        build_dir = paths.gclient_build_dir()
        f.create_dir(build_dir)
        _link_gclient_pdfium_slot(build_dir, root_pdfium)
        _ensure_gclient_android_only(build_dir)
        _clean_pdfium_deps_before_sync(root_pdfium)

        l.colored(
            "gclient sync can take several minutes (longer on Docker bind mounts).",
            l.YELLOW,
        )
        _run_gclient_sync(build_dir)

    if not _linux_host_toolchain_ready(root_pdfium):
        l.e(
            "Linux Chromium clang still wrong after gclient sync.\n"
            "  Check: file {}\n"
            "  Fix: rm -rf pdfium/third_party/llvm-build && "
            "PDFIUM_FORCE_DOCKER_BUILD=1 pnpm pdfium-build-android".format(clang_path)
        )

    l.colored("Linux host toolchain ready.", l.GREEN)


# -----------------------------------------------------------------------------
def ensure_ios_host_toolchain():
    """Ensure third_party/llvm-build clang matches this Mac (not Linux from Docker sync)."""
    if platform.system() != "Darwin":
        return

    root_pdfium = os.path.abspath(
        paths.resolve_pdfium_source_dir() or paths.DEFAULT_ROOT_PDFIUM
    )
    if _ios_host_toolchain_ready(root_pdfium):
        return

    clang_path = _llvm_clang_path(root_pdfium)
    if os.path.isfile(clang_path):
        description = _clang_binary_description(clang_path)
    else:
        description = "(missing)"

    l.colored(
        "Wrong or missing macOS Chromium clang at {} ({}). "
        "This often happens after gclient sync in Linux/Docker. "
        "Re-syncing DEPS for iOS...".format(clang_path, description),
        l.YELLOW,
    )

    llvm_build = os.path.join(root_pdfium, "third_party", "llvm-build")
    if os.path.isdir(llvm_build):
        f.remove_dir(llvm_build)

    cm.ensure_depot_tools_on_path()

    build_dir = paths.gclient_build_dir()
    f.create_dir(build_dir)
    _link_gclient_pdfium_slot(build_dir, root_pdfium)
    _ensure_gclient_ios_only(build_dir)
    _clean_pdfium_deps_before_sync(root_pdfium)

    l.colored("gclient sync can take several minutes.", l.YELLOW)
    _run_gclient_sync(build_dir)

    if not _ios_host_toolchain_ready(root_pdfium):
        l.e(
            "macOS Chromium clang still wrong after gclient sync.\n"
            "  Check: file {}\n"
            "  Fix: rm -rf pdfium/third_party/llvm-build && pnpm pdfium-init".format(
                clang_path
            )
        )

    l.colored("iOS host toolchain ready.", l.GREEN)


# -----------------------------------------------------------------------------
def get_pdfium_by_target(
    target,
    append_target_os=True,
    enable_v8=False,
    git_url=None,
    git_branch=None,
):
    """Legacy per-platform gclient checkout (macOS / WASM). Mobile uses get_pdfium_shared."""
    l.colored("Building PDFium...", l.YELLOW)
    cm.ensure_depot_tools_on_path()

    resolved_url = git_url or "https://pdfium.googlesource.com/pdfium.git"
    resolved_branch = git_branch or c.pdfium_git_branch

    build_dir = os.path.join("build", target)
    f.create_dir(build_dir)

    l.colored("Removing old PDFium directory...", l.YELLOW)
    target_dir = os.path.join(build_dir, "pdfium")
    f.remove_dir(target_dir)

    l.colored("Cloning PDFium with gclient...", l.YELLOW)
    config_args = [
        "gclient",
        "config",
        "--unmanaged",
        resolved_url,
    ]

    if not enable_v8:
        config_args.extend(["--custom-var", "checkout_configuration=minimal"])

    r.run(config_args, cwd=build_dir)

    if append_target_os:
        l.colored(
            "Appending target os ({}) to gclient file...".format(target),
            l.YELLOW,
        )
        gclient_file = os.path.join(build_dir, ".gclient")
        f.append_to_file(gclient_file, "target_os = [ '{}' ]".format(target))

    l.colored(f"Syncing repository with branch {resolved_branch}...", l.YELLOW)
    r.run(
        [
            "gclient",
            "sync",
            "-r",
            f"origin/{resolved_branch}",
            "--no-history",
            "--shallow",
        ],
        cwd=build_dir,
    )

    _reset_gclient_folders(build_dir)
    l.ok()


# -----------------------------------------------------------------------------
def _is_git_checkout(path):
    git_path = os.path.join(path, ".git")
    return os.path.isdir(git_path) or os.path.isfile(git_path)


def _clean_stale_shared_checkout(build_dir, root_pdfium):
    """Remove failed gclient dirs under build/shared/ (not pdfium-lib/pdfium/)."""
    nested = os.path.join(build_dir, "pdfium")
    root_abs = os.path.abspath(root_pdfium)
    if os.path.lexists(nested):
        nested_abs = os.path.abspath(os.path.realpath(nested))
        if nested_abs != root_abs:
            if os.path.islink(nested):
                os.remove(nested)
            else:
                f.remove_dir(nested)

    bad_scm = os.path.join(build_dir, "_bad_scm")
    if os.path.isdir(bad_scm):
        f.remove_dir(bad_scm)


def _configure_shared_gclient(build_dir, enable_v8):
    config_args = [
        "gclient",
        "config",
        "--unmanaged",
        "pdfium",
    ]
    if not enable_v8:
        config_args.extend(["--custom-var", "checkout_configuration=minimal"])

    r.run(config_args, cwd=build_dir)

    target_os = ", ".join(f'"{t}"' for t in _shared_target_os_list())
    gclient_file = os.path.join(build_dir, ".gclient")
    f.append_to_file(gclient_file, f"target_os = [ {target_os} ]")


def _link_gclient_pdfium_slot(build_dir, root_pdfium):
    """Symlink build/shared/pdfium -> pdfium-lib/pdfium/ before gclient sync."""
    slot = os.path.join(build_dir, "pdfium")
    root_abs = os.path.abspath(root_pdfium)
    parent = os.path.dirname(slot)
    os.makedirs(parent, exist_ok=True)

    if os.path.lexists(slot):
        slot_abs = os.path.abspath(os.path.realpath(slot))
        if slot_abs == root_abs:
            return
        if os.path.islink(slot):
            os.remove(slot)
        else:
            f.remove_dir(slot)

    os.symlink(os.path.relpath(root_abs, parent), slot)


def _shared_target_os_list():
    """Host-specific target_os so gclient does not install the wrong LLVM toolchain."""
    if platform.system() == "Darwin":
        return ["ios"]
    return ["android"]


def _android_llvm_deps_ready(root_pdfium):
    import glob

    pattern = os.path.join(
        root_pdfium,
        "third_party",
        "llvm-build",
        "Release+Asserts",
        "lib",
        "clang",
        "*",
        "lib",
        "linux",
    )
    return bool(glob.glob(pattern))


def _android_toolchain_sysroot_header(root_pdfium):
    return os.path.join(
        root_pdfium,
        "third_party",
        "android_toolchain",
        "ndk",
        "toolchains",
        "llvm",
        "prebuilt",
        "linux-x86_64",
        "sysroot",
        "usr",
        "include",
        "alloca.h",
    )


def _android_toolchain_ready(root_pdfium):
    return os.path.isfile(_android_toolchain_sysroot_header(root_pdfium))


def _android_deps_ready(root_pdfium):
    return _android_llvm_deps_ready(root_pdfium) and _android_toolchain_ready(
        root_pdfium
    )


def _docker_android_toolchain_cache_dir():
    return "/opt/pdfium-android-toolchain"


def _restore_docker_android_toolchain(root_pdfium):
    cache_dir = _docker_android_toolchain_cache_dir()
    if not os.path.isdir(cache_dir):
        return False

    if _android_toolchain_ready(root_pdfium):
        return True

    l.colored(
        "Restoring Android NDK toolchain from Docker image cache...",
        l.YELLOW,
    )
    dest = os.path.join(root_pdfium, "third_party", "android_toolchain")
    if os.path.isdir(dest):
        f.remove_dir(dest)

    shutil.copytree(cache_dir, dest, symlinks=True)
    return _android_toolchain_ready(root_pdfium)


def _llvm_clang_path(root_pdfium):
    return os.path.join(
        root_pdfium,
        "third_party",
        "llvm-build",
        "Release+Asserts",
        "bin",
        "clang++",
    )


def _clang_binary_description(clang_path):
    try:
        result = subprocess.run(
            ["file", "-bL", clang_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def _expected_mac_clang_arch():
    machine = platform.machine().lower()
    if machine == "arm64":
        return "arm64"
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    return machine


def _ios_host_toolchain_ready(root_pdfium):
    clang_path = _llvm_clang_path(root_pdfium)
    if not os.path.isfile(clang_path) or not os.access(clang_path, os.X_OK):
        return False

    description = _clang_binary_description(clang_path)
    if "Mach-O" not in description:
        return False

    expected_arch = _expected_mac_clang_arch()
    return expected_arch in description


def _linux_host_toolchain_ready(root_pdfium):
    clang_path = _llvm_clang_path(root_pdfium)
    if not os.path.isfile(clang_path) or not os.access(clang_path, os.X_OK):
        return False

    description = _clang_binary_description(clang_path)
    if "ELF" not in description:
        return False

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86-64" in description
    if machine == "aarch64":
        return "aarch64" in description or "ARM" in description
    return True


def _linux_gn_paths(root_pdfium):
    buildtools = os.path.join(root_pdfium, "buildtools", "linux64")
    return [
        os.path.join(buildtools, "gn", "gn"),
        os.path.join(buildtools, "gn"),
    ]


def _linux_buildtools_ready(root_pdfium):
    for gn_path in _linux_gn_paths(root_pdfium):
        if not os.path.isfile(gn_path) or not os.access(gn_path, os.X_OK):
            continue
        if "ELF" in _clang_binary_description(gn_path):
            return True
    return False


def _docker_buildtools_cache_dir():
    return "/opt/pdfium-buildtools/linux64"


def _restore_docker_buildtools(root_pdfium):
    cache_dir = _docker_buildtools_cache_dir()
    if not os.path.isdir(cache_dir):
        return False

    if _linux_buildtools_ready(root_pdfium):
        return True

    l.colored(
        "Restoring Linux buildtools from Docker image cache...",
        l.YELLOW,
    )
    dest = os.path.join(root_pdfium, "buildtools", "linux64")
    if os.path.isdir(dest):
        f.remove_dir(dest)

    os.makedirs(os.path.join(root_pdfium, "buildtools"), exist_ok=True)
    shutil.copytree(cache_dir, dest, symlinks=True)
    return _linux_buildtools_ready(root_pdfium)


def _docker_llvm_cache_dir():
    return "/opt/pdfium-llvm-build"


def _restore_docker_llvm_cache(root_pdfium):
    cache_dir = _docker_llvm_cache_dir()
    if not os.path.isdir(cache_dir):
        return False

    clang_path = _llvm_clang_path(root_pdfium)
    if _linux_host_toolchain_ready(root_pdfium):
        return True

    l.colored(
        "Restoring Linux llvm-build from Docker image cache...",
        l.YELLOW,
    )
    llvm_build = os.path.join(root_pdfium, "third_party", "llvm-build")
    if os.path.isdir(llvm_build):
        f.remove_dir(llvm_build)

    shutil.copytree(cache_dir, llvm_build, symlinks=True)
    return _linux_host_toolchain_ready(root_pdfium)


def _run_gclient_sync(build_dir):
    r.run(
        ["gclient", "sync", "--no-history", "--shallow"],
        cwd=build_dir,
    )


def _ensure_gclient_ios_only(build_dir, enable_v8=False):
    gclient_file = os.path.join(build_dir, ".gclient")
    if not os.path.isfile(gclient_file):
        _configure_shared_gclient(build_dir, enable_v8)
        return

    if _read_gclient_target_os(gclient_file) == {"ios"}:
        return

    _write_gclient_target_os(gclient_file, {"ios"})


def _ensure_gclient_android_only(build_dir, enable_v8=False):
    gclient_file = os.path.join(build_dir, ".gclient")
    if not os.path.isfile(gclient_file):
        _configure_shared_gclient(build_dir, enable_v8)
        return

    if _read_gclient_target_os(gclient_file) == {"android"}:
        return

    _write_gclient_target_os(gclient_file, {"android"})


def _read_gclient_target_os(gclient_file):
    with open(gclient_file, encoding="utf-8") as handle:
        content = handle.read()
    match = re.search(r"target_os\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def _write_gclient_target_os(gclient_file, targets):
    with open(gclient_file, encoding="utf-8") as handle:
        content = handle.read()
    new_line = "target_os = [ {} ]".format(
        ", ".join(f'"{target}"' for target in sorted(targets))
    )
    if re.search(r"target_os\s*=", content):
        content = re.sub(r"target_os\s*=\s*\[[^\]]*\]", new_line, content)
    else:
        content = content.rstrip() + "\n" + new_line + "\n"
    with open(gclient_file, "w", encoding="utf-8") as handle:
        handle.write(content)


def _ensure_gclient_has_android(build_dir, enable_v8=False):
    gclient_file = os.path.join(build_dir, ".gclient")
    if not os.path.isfile(gclient_file):
        _configure_shared_gclient(build_dir, enable_v8)
        if "android" not in _read_gclient_target_os(gclient_file):
            targets = _read_gclient_target_os(gclient_file) | {"android"}
            _write_gclient_target_os(gclient_file, targets)
        return

    targets = _read_gclient_target_os(gclient_file)
    if "android" in targets:
        return

    targets.add("android")
    _write_gclient_target_os(gclient_file, targets)


# -----------------------------------------------------------------------------
def _reset_gclient_folders(build_dir):
    folders_to_reset = [
        "pdfium",
        "pdfium/build",
        "pdfium/third_party/libjpeg_turbo",
        "pdfium/base/allocator/partition_allocator",
    ]

    for folder in folders_to_reset:
        full_path = os.path.join(build_dir, folder)

        if os.path.exists(full_path):
            r.run(["git", "reset", "--hard"], cwd=full_path)
            r.run(["git", "clean", "-df"], cwd=full_path)


# -----------------------------------------------------------------------------
def _pdfium_deps_subtree_paths(root_pdfium):
    return [
        os.path.join(root_pdfium, "build"),
        os.path.join(root_pdfium, "third_party", "libjpeg_turbo"),
        os.path.join(root_pdfium, "base", "allocator", "partition_allocator"),
    ]


def _reset_git_subtrees(paths):
    for full_path in paths:
        if os.path.isdir(os.path.join(full_path, ".git")):
            r.run(["git", "reset", "--hard"], cwd=full_path)
            r.run(["git", "clean", "-df"], cwd=full_path)


def _clean_pdfium_deps_before_sync(root_pdfium):
    """gclient sync fails if DEPS repos are dirty (e.g. after patch-ios)."""
    deps_paths = _pdfium_deps_subtree_paths(root_pdfium)
    if not any(os.path.isdir(os.path.join(p, ".git")) for p in deps_paths):
        return
    l.colored(
        "Resetting PDFium DEPS checkouts before gclient sync "
        "(re-run patch-ios / patch-android after sync)...",
        l.YELLOW,
    )
    _reset_git_subtrees(deps_paths)


def _reset_pdfium_subtrees(root_pdfium):
    _reset_git_subtrees([root_pdfium] + _pdfium_deps_subtree_paths(root_pdfium))
