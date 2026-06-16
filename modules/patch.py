import os

from pygemstones.io import file as f
from pygemstones.util import log as l

import modules.pdfium_paths as paths


# -----------------------------------------------------------------------------
def apply_shared_library(target):
    """Android needs libpdfium.so; accept upstream component or iOS static_library."""
    source_dir = paths.pdfium_source_dir(target)
    source_file = os.path.join(source_dir, "BUILD.gn")

    shared_content = 'shared_library("pdfium") {'
    if f.file_has_content(source_file, shared_content):
        l.bullet("Skipped: shared library (already applied)", l.PURPLE)
        return

    for original_content in ('component("pdfium") {', 'static_library("pdfium") {'):
        if f.file_has_content(source_file, original_content):
            f.replace_in_file(source_file, original_content, shared_content)
            l.bullet("Applied: shared library", l.GREEN)
            return

    l.bullet("Skipped: shared library", l.PURPLE)


# -----------------------------------------------------------------------------
def apply_static_library(target):
    """iOS xcframework expects libpdfium.a; fork BUILD.gn may use shared_library."""
    source_dir = paths.pdfium_source_dir(target)
    source_file = os.path.join(source_dir, "BUILD.gn")

    original_content = 'shared_library("pdfium") {'
    has_content = f.file_has_content(source_file, original_content)

    if has_content:
        new_content = 'static_library("pdfium") {'
        f.replace_in_file(source_file, original_content, new_content)
        l.bullet("Applied: static library", l.GREEN)
    else:
        l.bullet("Skipped: static library", l.PURPLE)
        return

    component_type_line = '    static_component_type = "static_library"\n'
    if f.file_has_content(source_file, component_type_line.strip()):
        f.replace_in_file(source_file, component_type_line, "")
        l.bullet("Applied: static library complete-lib fix", l.GREEN)


# -----------------------------------------------------------------------------
def apply_public_headers(target):
    source_dir = paths.pdfium_source_dir(target)
    public_dir = os.path.join(source_dir, "public")

    # file: public/fpdfview.h (p1)
    source_file = os.path.join(public_dir, "fpdfview.h")

    original_content = "#if defined(COMPONENT_BUILD)\n// FPDF_EXPORT should be consistent with |export| in the pdfium_fuzzer\n// template in testing/fuzzers/BUILD.gn."
    has_content = f.file_has_content(source_file, original_content)

    if has_content:
        f.replace_in_file(source_file, original_content, "")
        l.bullet("Applied: public headers (p1)", l.GREEN)
    else:
        l.bullet("Skipped: public headers (p1)", l.PURPLE)

    # file: public/fpdfview.h (p2)
    source_file = os.path.join(public_dir, "fpdfview.h")

    original_content = "#else\n#define FPDF_EXPORT\n#endif  // defined(COMPONENT_BUILD)"
    has_content = f.file_has_content(source_file, original_content)

    if has_content:
        f.replace_in_file(source_file, original_content, "")
        l.bullet("Applied: public headers (p2)", l.GREEN)
    else:
        l.bullet("Skipped: public headers (p2)", l.PURPLE)
