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
    # Clone the Windows pdfium fork. The target "win" is used as BOTH the build
    # directory name (build/win/pdfium) AND the gclient target_os value, which
    # is the value Chromium's gclient recognizes for Windows. Using "win"
    # everywhere means the build dir name and the gclient os no longer need to
    # be decoupled.
    p.get_pdfium_by_target(
        "win",
        git_url=c.pdfium_win_git_url,
        git_branch=c.pdfium_win_git_branch,
    )


# -----------------------------------------------------------------------------
def run_task_patch():
    l.colored("Patching files...", l.YELLOW)

    # shared lib
    if c.shared_lib_windows:
        patch.apply_shared_library("win")

    # public headers
    #
    # CRITICAL for Windows: this strips the COMPONENT_BUILD guard from
    # public/fpdfview.h so that __declspec(dllexport) is active whenever
    # FPDF_IMPLEMENTATION is defined (we define it via extra_cflags in
    # common.get_build_args for target_os == "win"). Without this patch a
    # non-component Windows DLL would export ZERO symbols and
    # pdfium-render's Pdfium::bind_to_library would fail to resolve any
    # LMP_*/FPDF* function by name.
    if c.shared_lib_windows:
        patch.apply_public_headers("win")

    l.ok()


# -----------------------------------------------------------------------------
def run_task_build():
    l.colored("Building libraries...", l.YELLOW)

    current_dir = f.current_dir()

    # configs
    for config in c.configurations_windows:
        # targets
        for target in c.targets_windows:
            main_dir = os.path.join(
                "build",
                "win",
                "pdfium",
                "out",
                "{0}-{1}-{2}".format(target["target_os"], target["target_cpu"], config),
            )

            f.recreate_dir(main_dir)

            os.chdir(
                os.path.join(
                    "build",
                    "win",
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
                c.shared_lib_windows,
                target["pdfium_os"],
                target["target_cpu"],
            )

            # out dir relative to the pdfium source dir we just chdir'd into.
            # (main_dir above is relative to the pdfium-lib root; here, after
            # the chdir, the same directory is just "out/<dir>".)
            out_dir = "out/{0}-{1}-{2}".format(
                target["target_os"], target["target_cpu"], config
            )

            # Windows shell quoting fix:
            #
            # The macos/android flow passes the gn args inline as
            # "--args='{0}'" through a POSIX shell, which strips the single
            # quotes so gn receives the bare args string. On Windows
            # subprocess(shell=True) invokes cmd.exe, which does NOT treat
            # single quotes as delimiters, so gn would receive a literal
            # leading quote and error. Dropping the quotes is also wrong: the
            # args contain spaces AND embedded double quotes (e.g.
            # extra_cflags="/DFPDF_IMPLEMENTATION").
            #
            # Avoid the cmd.exe quoting problem by keeping the args off the
            # command line: gn reads "<out-dir>/args.gn" automatically, so we
            # write the args there (one per line for readability) and run
            # "gn gen <out-dir>" with no --args. (We still run gn via shell=True
            # below so cmd.exe can resolve its .bat wrapper.) We write
            # args.gn AFTER the chdir, to the cwd-relative out_dir. The out dir
            # itself already exists because f.recreate_dir(main_dir) above
            # created it (main_dir is the same directory pre-chdir).
            args_gn_content = "\n".join(args) + "\n"
            f.set_file_content(os.path.join(out_dir, "args.gn"), args_gn_content)

            # depot_tools' gn is a .bat wrapper on Windows, which subprocess
            # cannot launch without a shell, so run via shell=True. Quoting is
            # not a concern: the build args live in args.gn (written above), so
            # "gn gen <out-dir>" has no special characters. Do NOT add --args.
            r.run("gn gen {0}".format(out_dir), shell=True)

            # compiling...
            l.colored(
                'Compiling to arch "{0}" and configuration "{1}"...'.format(
                    target["target_cpu"], config
                ),
                l.YELLOW,
            )

            # The ninja target for a DLL is "pdfium" (the shared_library, after
            # the apply_shared_library patch renames component("pdfium") to
            # shared_library("pdfium")). depot_tools' ninja is a .bat wrapper on
            # Windows, so run via shell=True; the args have no special chars.
            r.run("ninja -C {0} pdfium -v".format(out_dir), shell=True)

            os.chdir(current_dir)

    l.ok()


# -----------------------------------------------------------------------------
def run_task_install():
    l.colored("Installing libraries...", l.YELLOW)

    # configs
    for config in c.configurations_windows:
        f.recreate_dir(os.path.join("build", "win", config))
        f.create_dir(os.path.join("build", "win", config, "lib"))

        # targets
        for target in c.targets_windows:
            out_dir = "{0}-{1}-{2}".format(
                target["target_os"], target["target_cpu"], config
            )

            source_out_dir = os.path.join(
                "build",
                "win",
                "pdfium",
                "out",
                out_dir,
            )

            target_lib_dir = os.path.join("build", "win", config, "lib")

            # Copy the DLL and its import library.
            #
            # For a shared_library("pdfium") with output_name = "pdfium",
            # ninja on Windows emits the runtime DLL and its import library in
            # the OUT DIR ROOT (not under obj/):
            #     out/<config>/pdfium.dll       (the runtime library)
            #     out/<config>/pdfium.dll.lib   (the import library)
            # plus pdfium.dll.pdb (debug symbols) for debug configs.
            #
            # NO lipo on Windows (single x64 arch only).
            #
            # VERIFY on a real Windows host: confirm the exact emitted
            # filenames. PDFium/GN typically produces "pdfium.dll" and
            # "pdfium.dll.lib"; some toolchain configurations emit
            # "pdfium.lib" as the import library instead. We copy any of
            # {*.dll, *.dll.lib, *.lib} found in the out dir root to be safe.
            for basename in os.listdir(source_out_dir):
                lower = basename.lower()
                is_dll = lower.endswith(".dll")
                is_import_lib = lower.endswith(".dll.lib") or lower == "pdfium.lib"
                is_pdb = lower.endswith(".dll.pdb")

                if is_dll or is_import_lib or is_pdb:
                    pathname = os.path.join(source_out_dir, basename)

                    if os.path.isfile(pathname):
                        f.copy_file(
                            pathname,
                            os.path.join(target_lib_dir, basename),
                        )

            # fix include path
            source_include_path = os.path.join(
                "build",
                "win",
                "pdfium",
                "public",
            )

            headers = f.find_files(source_include_path, "*.h", True)

            for header in headers:
                f.replace_in_file(header, '#include "public/', '#include "../')

        # file data
        lib_file_out = os.path.join(
            "build", "win", config, "lib", "pdfium.dll"
        )

        if os.path.isfile(lib_file_out):
            # cmd.exe has no "ls"; report the size with stdlib instead of
            # shelling out to a Unix command.
            l.colored("File size...", l.YELLOW)
            size_bytes = os.path.getsize(lib_file_out)
            size_mb = size_bytes / (1024 * 1024)
            l.m("{0} ({1} bytes, {2:.2f} MB)".format(lib_file_out, size_bytes, size_mb))

        # headers
        l.colored("Copying header files...", l.YELLOW)

        include_dir = os.path.join("build", "win", "pdfium", "public")
        include_cpp_dir = os.path.join(include_dir, "cpp")
        target_include_dir = os.path.join("build", "win", config, "include")
        target_include_cpp_dir = os.path.join(target_include_dir, "cpp")

        f.recreate_dir(target_include_dir)
        f.copy_files(include_dir, target_include_dir, "*.h")
        f.copy_files(include_cpp_dir, target_include_cpp_dir, "*.h")

    l.ok()


# -----------------------------------------------------------------------------
def run_task_archive():
    l.colored("Archiving...", l.YELLOW)

    current_dir = f.current_dir()
    lib_dir = os.path.join(current_dir, "build", "win")
    output_filename = os.path.join(current_dir, "win.tgz")

    tar = tarfile.open(output_filename, "w:gz")

    # Exclude intermediate files (those with "_" in their archive name) while
    # always keeping the artifacts we want: headers and the build outputs
    # (.dll / .lib / .pdb). x.name is the archive-relative name, so we must NOT
    # call os.path.isfile(x.name) here — it won't resolve from the cwd and the
    # macOS original (which we mirror) does no such check.
    def archive_filter(tarinfo):
        keep_suffixes = (".h", ".dll", ".lib", ".pdb")
        is_intermediate = "_" in tarinfo.name and not tarinfo.name.endswith(
            keep_suffixes
        )
        return None if is_intermediate else tarinfo

    for configuration in c.configurations_windows:
        tar.add(
            name=os.path.join(lib_dir, configuration),
            arcname=os.path.basename(os.path.join(lib_dir, configuration)),
            filter=archive_filter,
        )

    tar.close()

    l.ok()
