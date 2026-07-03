# Build for Linux

1. First, execute all steps in the [How to compile](https://github.com/paulocoutinhox/pdfium-lib/tree/master?tab=readme-ov-file#how-to-compile) section

2. Get PDFium:
```python3 make.py build-pdfium-linux```

3. PDFium Linux dependencies:
```
cd build/linux/pdfium
echo n | ./build/install-build-deps.sh
cd ../../..
```

4. Patch:
```python3 make.py patch-linux```

5. Compile:
```python3 make.py build-linux```

6. Install libraries:
```python3 make.py install-linux```

7. Test:
```python3 make.py test-linux```

Obs:
- The file **make.py** need be executed with python version 3.
- You need run all steps in a Linux machine (real, vm or docker) to it works.

## OrbStack (macOS)

If you're on macOS, [OrbStack](https://orbstack.dev/) gives you a real Linux VM to run these steps without Docker:

1. Create an **amd64** VM: `orb create -a amd64 ubuntu`. On Apple Silicon, don't use the default (arm64) architecture — PDFium's `DEPS` unconditionally fetches a `buildtools/reclient` CIPD package with no `linux-arm64` build for the pinned version, so `gclient sync` fails outright on an arm64 Linux host no matter which architecture you're trying to build for. `amd64` (run under OrbStack's emulation) avoids this entirely.
2. Open a shell in it: `orb shell -m <machine-name>`
3. `cd` to this repo through the automatic macOS mount, e.g. `cd /mnt/mac/Users/<you>/path/to/pdfium-lib`
4. Run the steps above from inside that shell.

Obs: for anything beyond a quick check, copy this repo into the VM's own filesystem (e.g. `~/pdfium-lib`) instead of working directly on the `/mnt/mac/...` mount — PDFium's checkout has hundreds of thousands of small files, and building across that mount is significantly slower than building on the VM's native disk. Copy the `build/linux/<config>/` output back out through the mount when you're done.
