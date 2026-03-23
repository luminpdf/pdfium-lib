import os

from pygemstones.io import file as f
from pygemstones.system import runner as r
from pygemstones.util import log as l

import modules.config as c


# -----------------------------------------------------------------------------
def get_pdfium_by_target(target, append_target_os=True, enable_v8=False):
    l.colored("Building PDFium...", l.YELLOW)

    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    local_pdfium_path = os.path.abspath(os.path.join(current_file_dir, "..", "..", "pdfium"))

    build_dir = os.path.join("build", target)
    f.create_dir(build_dir)

    # remove old data
    l.colored("Removing old PDFium directory...", l.YELLOW)
    target_dir = os.path.join(build_dir, "pdfium")
    f.remove_dir(target_dir)

    # copy local source to build directory
    l.colored(f"Copying PDFium source from {local_pdfium_path}...", l.YELLOW)
    f.copy_dir(local_pdfium_path, target_dir)

    # initialize temporary git in the copy to satisfy gclient
    l.colored("Initializing temporary git in build copy...", l.YELLOW)
    r.run(["git", "init"], cwd=target_dir)
    r.run(["git", "add", "."], cwd=target_dir)
    r.run(["git", "commit", "--allow-empty", "-m", "local-build-sync"], cwd=target_dir)

    # configure gclient
    l.colored("Configuring gclient...", l.YELLOW)
    config_args = [
        "gclient",
        "config",
        "--unmanaged",
        "pdfium",
    ]

    if not enable_v8:
        config_args.extend(["--custom-var", "checkout_configuration=minimal"])

    r.run(config_args, cwd=build_dir)

    # append target os
    if append_target_os:
        l.colored(
            "Appending target os ({}) to gclient file...".format(target),
            l.YELLOW,
        )
        gclient_file = os.path.join(build_dir, ".gclient")
        f.append_to_file(gclient_file, "target_os = [ '{}' ]".format(target))

    # remove any parent .git file/dir that could confuse gclient's git commands
    # (e.g. submodule pointer from host volume mount)
    root_git = os.path.join(os.getcwd(), ".git")
    root_git_backup = None
    if os.path.isfile(root_git):
        root_git_backup = root_git + ".bak"
        l.colored("Temporarily hiding root .git submodule pointer...", l.YELLOW)
        os.rename(root_git, root_git_backup)

    try:
        l.colored("Syncing dependencies...", l.YELLOW)
        r.run(
            [
                "gclient",
                "sync",
                "--no-history",
                "--shallow",
            ],
            cwd=build_dir,
        )
    finally:
        if root_git_backup and os.path.exists(root_git_backup):
            os.rename(root_git_backup, root_git)

    l.ok()