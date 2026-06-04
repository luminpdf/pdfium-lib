import glob
import os
import shutil

# pdfium-lib/modules -> pdfium-lib
PDFIUM_LIB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Parent app repo (rn-lumin-pdf)
REPO_ROOT = os.path.abspath(os.path.join(PDFIUM_LIB_ROOT, ".."))

GCLIENT_SHARED_DIR = "shared"
DEFAULT_ROOT_PDFIUM = os.path.join(PDFIUM_LIB_ROOT, "pdfium")


def repo_root():
    return REPO_ROOT


def pdfium_lib_root():
    return PDFIUM_LIB_ROOT


def resolve_pdfium_source_dir():
    """Absolute path to the shared PDFium checkout, or None for legacy per-platform trees."""
    env = os.environ.get("PDFIUM_SOURCE_DIR")
    if env:
        path = os.path.abspath(env)
        if os.path.isfile(os.path.join(path, "BUILD.gn")):
            return path
        return None

    if os.path.isfile(os.path.join(DEFAULT_ROOT_PDFIUM, "BUILD.gn")):
        return DEFAULT_ROOT_PDFIUM

    return None


def using_shared_pdfium_source():
    return resolve_pdfium_source_dir() is not None


def pdfium_source_dir(platform):
    """Directory containing PDFium BUILD.gn (shared pdfium-lib/pdfium or legacy build/<platform>/pdfium)."""
    shared = resolve_pdfium_source_dir()
    if shared:
        return shared

    return os.path.abspath(os.path.join(os.getcwd(), "build", platform, "pdfium"))


def gclient_build_dir():
    return os.path.join("build", GCLIENT_SHARED_DIR)


def cleanup_legacy_platform_build_dirs():
    """Remove stale per-platform gclient state; keep build/<platform>/release/ artifacts."""
    cwd = os.getcwd()
    for platform in ("ios", "android"):
        platform_dir = os.path.join(cwd, "build", platform)
        if not os.path.isdir(platform_dir):
            continue

        for pattern in (".gclient", ".gclient_*", ".gcs_entries"):
            for path in glob.glob(os.path.join(platform_dir, pattern)):
                if os.path.isfile(path):
                    os.remove(path)

        cipd_dir = os.path.join(platform_dir, ".cipd")
        if os.path.isdir(cipd_dir):
            shutil.rmtree(cipd_dir)

        pdfium_path = os.path.join(platform_dir, "pdfium")
        if os.path.islink(pdfium_path):
            os.remove(pdfium_path)
        elif os.path.isdir(pdfium_path):
            source = resolve_pdfium_source_dir()
            if not source or not os.path.samefile(pdfium_path, source):
                shutil.rmtree(pdfium_path)
