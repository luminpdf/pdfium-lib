import os
import platform

from pygemstones.io import file as f
from pygemstones.system import runner as r
from pygemstones.util import log as l

import modules.common as cm
import modules.config as c
import modules.pdfium_paths as paths


# -----------------------------------------------------------------------------
def get_pdfium_shared(
    enable_v8=False,
    git_url=None,
    git_branch=None,
):
    """Sync PDFium + DEPS into pdfium-lib/pdfium/ (shared by iOS and Android)."""
    l.colored("Building PDFium (shared mobile source)...", l.YELLOW)
    cm.ensure_depot_tools_on_path()

    resolved_url = git_url or c.pdfium_mobile_git_url
    resolved_branch = git_branch or c.pdfium_mobile_git_branch

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
    _write_shared_gclient(build_dir, resolved_url, enable_v8)

    _checkout_pdfium_branch(root_pdfium, resolved_branch)

    _clean_pdfium_deps_before_sync(root_pdfium)

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

    _reset_pdfium_subtrees(root_pdfium)

    if not os.path.isfile(os.path.join(root_pdfium, "BUILD.gn")):
        l.e(
            f"PDFium source missing BUILD.gn at {root_pdfium}. "
            "Run: git submodule update --init --recursive pdfium-lib"
        )

    l.ok()


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


def _checkout_pdfium_branch(root_pdfium, branch):
    """Align pdfium-lib/pdfium/ with the branch gclient will sync (avoids branch switch errors)."""
    remote_ref = f"origin/{branch}"
    l.colored(f"Checking out {branch} in pdfium source...", l.YELLOW)
    r.run(["git", "fetch", "origin", branch], cwd=root_pdfium)
    r.run(
        ["git", "checkout", "-B", branch, remote_ref],
        cwd=root_pdfium,
    )


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


def _write_shared_gclient(build_dir, git_url, enable_v8):
    vars_line = ""
    if not enable_v8:
        vars_line = '    "custom_vars": {"checkout_configuration": "minimal"},\n'

    target_os = ", ".join(f'"{t}"' for t in _shared_target_os_list())
    content = f"""solutions = [
  {{ "name": "pdfium",
    "url": "{git_url}",
    "deps_file": "DEPS",
    "managed": False,
{vars_line}  }},
]
target_os = [ {target_os} ]
"""
    gclient_file = os.path.join(build_dir, ".gclient")
    with open(gclient_file, "w", encoding="utf-8") as handle:
        handle.write(content)


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
