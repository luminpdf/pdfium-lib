# general
debug = False
task = ""

# pdfium
pdfium_git_branch = "main"
# ^ ref: https://github.com/luminpdf/pdfium
# OBS 1: don't forget change in android docker file (docker/android/Dockerfile)
# OBS 2: don't forget change in wasm docker file (docker/wasm/Dockerfile)

# iOS / Android use a custom fork instead of the upstream Google mirror
pdfium_mobile_git_url = "git@github.com:luminpdf/pdfium.git"
pdfium_mobile_git_branch = "luminpdf-mobile/main"

# Windows uses a custom fork instead of the upstream Google mirror
pdfium_win_git_url = "git@github.com:luminpdf/pdfium.git"
pdfium_win_git_branch = "luminpdf/main"

# emsdk
emsdk_version = "4.0.15"
# OBS 1: don't forget change in wasm docker file (docker/wasm/Dockerfile)

# macos
configurations_macos = ["release"]
shared_lib_macos = False
targets_macos = [
    {"target_os": "macos", "target_cpu": "x64", "pdfium_os": "mac"},
    {"target_os": "macos", "target_cpu": "arm64", "pdfium_os": "mac"},
]

# windows
configurations_windows = ["release"]
shared_lib_windows = True
# ^ DLL build (required so the shared-library + dllexport patches run).
# x64 ONLY: FPDF_CALLCONV is __stdcall; pdfium-render bindings are extern "C",
# which matches the calling convention only on x64 (mismatches x86).
targets_windows = [
    {"target_os": "win", "target_cpu": "x64", "pdfium_os": "win"},
]

# ios
configurations_ios = ["release"]
shared_lib_ios = False
targets_ios = [
    {
        "target_os": "ios",
        "target_cpu": "arm64",
        "pdfium_os": "ios",
        "target_environment": "device",
    },
    {
        "target_os": "ios",
        "target_cpu": "x64",
        "pdfium_os": "ios",
        "target_environment": "simulator",
    },
    {
        "target_os": "ios",
        "target_cpu": "arm64",
        "pdfium_os": "ios",
        "target_environment": "simulator",
    },
]

# android
configurations_android = ["release"]
shared_lib_android = True
targets_android = [
    {
        "target_os": "android",
        "target_cpu": "arm",
        "pdfium_os": "android",
        "android_cpu": "armeabi-v7a",
    },
    {
        "target_os": "android",
        "target_cpu": "x86",
        "pdfium_os": "android",
        "android_cpu": "x86",
    },
    {
        "target_os": "android",
        "target_cpu": "arm64",
        "pdfium_os": "android",
        "android_cpu": "arm64-v8a",
    },
    {
        "target_os": "android",
        "target_cpu": "x64",
        "pdfium_os": "android",
        "android_cpu": "x86_64",
    },
]

# wasm
configurations_wasm = ["release"]
shared_lib_wasm = False
targets_wasm = [
    {"target_os": "emscripten", "target_cpu": "wasm", "pdfium_os": "emscripten"},
]

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
