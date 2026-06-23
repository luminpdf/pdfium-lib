import os

from pygemstones.io import file as f
from pygemstones.system import runner as r
from pygemstones.util import log as l

import modules.config as c


# -----------------------------------------------------------------------------
def get_pdfium_by_target(
    target,
    append_target_os=True,
    enable_v8=False,
    git_url=None,
    git_branch=None,
):
    l.colored("Building PDFium...", l.YELLOW)

    resolved_url = git_url or "https://pdfium.googlesource.com/pdfium.git"
    resolved_branch = git_branch or c.pdfium_git_branch

    build_dir = os.path.join("build", target)
    f.create_dir(build_dir)

    # remove old data
    l.colored("Removing old PDFium directory...", l.YELLOW)
    target_dir = os.path.join(build_dir, "pdfium")
    f.remove_dir(target_dir)

    # clone pdfium
    l.colored("Cloning PDFium with gclient...", l.YELLOW)
    config_args = [
        "gclient",
        "config",
        "--unmanaged",
        resolved_url,
    ]

    if not enable_v8:
        config_args.extend(["--custom-var", "checkout_configuration=minimal"])

    # Run via shell=True with a space-joined string. depot_tools' gclient is a
    # .bat wrapper on Windows; subprocess without a shell cannot launch a .bat
    # (CreateProcess only auto-appends .exe). shell=True lets cmd.exe resolve it
    # via PATHEXT, and is cross-platform safe (POSIX /bin/sh -c handles the same
    # string). The args are simple flags/URLs with no spaces or shell
    # metacharacters, so joining with spaces is safe.
    r.run(" ".join(config_args), cwd=build_dir, shell=True)

    # append target os
    if append_target_os:
        l.colored(
            "Appending target os ({}) to gclient file...".format(target),
            l.YELLOW,
        )
        gclient_file = os.path.join(build_dir, ".gclient")
        f.append_to_file(gclient_file, "target_os = [ '{}' ]".format(target))

    l.colored(f"Syncing repository with branch {resolved_branch}...", l.YELLOW)
    # shell=True with a space-joined string for the same .bat reason as the
    # gclient config call above (cross-platform safe; POSIX /bin/sh handles the
    # same string). Simple flag args, safe to join.
    r.run(
        " ".join(["gclient", "sync", "-r", f"origin/{resolved_branch}", "--no-history", "--shallow"]),
        cwd=build_dir,
        shell=True,
    )

    # reset and clean directories
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

    l.ok()
