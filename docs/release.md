# Releases

Field Shift is released as **one archive per system**, with everything it
needs inside (QGIS 4, Qt6, Python, the data libraries, PCSE and the
program): unpack and double-click the launcher.

| System | File | Launcher |
|--------|------|----------|
| Windows (x64) | `FieldShift-<version>-windows-x64.zip` | `FieldShift.bat` |
| Linux (x64) | `FieldShift-<version>-linux-x64.tar.gz` | `FieldShift.sh` |

About 1 GB each. The first start prepares the bundled runtime for its
folder (about a minute); the user's fields are saved in `app/terrenos/`.
See `README-RELEASE.txt`, copied into every archive from
`packaging/README-RELEASE.txt`. macOS is not built by the workflow (it does
not compile on the GitHub runners); a Mac can build its own archive with the
local build below, and its launcher is `FieldShift.command` (not signed:
macOS asks to confirm the first time). Android is not built (it cannot run
QGIS desktop / PyQt).

## Making a release

1. Set the version in `fieldshift/__init__.py`.
2. Push a tag with that version:

   ```bash
   git tag v1.0.0
   ```

   ```bash
   git push origin v1.0.0
   ```

3. `.github/workflows/release.yml` builds the two archives on Windows
   and Linux runners (about 30-60 minutes), checks that the Linux one
   starts, and publishes them as a GitHub Release.

"Run workflow" on the Actions page builds the archives without publishing
(they are attached to the run as artifacts).

## How an archive is built

`packaging/build_release.py --env <env prefix>` (needs `pip install
conda-pack`), on the system the archive is for:

1. the conda environment of `packaging/environment.yml` is packed with
   conda-pack into `runtime/`. Build it with `CONDA_OVERRIDE_ARCHSPEC=x86_64`
   on x86-64, or conda-forge picks builds tuned to the build machine's CPU
   that crash on older ones;
2. `fieldshift/`, `data/`, `docs/`, `LICENSE`, `README.md` (and the C++
   core if built) go into `app/`;
3. the launcher (`packaging/launchers/`) and `README-RELEASE.txt` are added;
   the launcher runs `conda-unpack` once, activates the runtime and starts
   `python -m fieldshift`.

Local build (Linux; the same commands work on macOS):

```bash
CONDA_OVERRIDE_ARCHSPEC=x86_64 micromamba create -n fs-release -f packaging/environment.yml
```

```bash
python packaging/build_release.py --env "$(micromamba info --base)/envs/fs-release"
```
