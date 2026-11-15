#!/usr/bin/env python3
"""Builds the release archive of Field Shift for the platform it runs on.

    python packaging/build_release.py --env <conda env prefix> [--out dist]

1. packs the conda environment (packaging/environment.yml: QGIS 4, data
   libraries, PCSE) with conda-pack into runtime/;
2. copies the program (fieldshift/, data/, docs/, LICENSE, README) into app/,
   and the C++ core library when it has been built (make cpp);
3. adds the launcher of the platform and README-RELEASE.txt;
4. writes FieldShift-<version>-<platform>.zip (Windows) or .tar.gz.

Each platform's archive must be built on that platform (QGIS is native
code): .github/workflows/release.yml does it on Windows, Linux and macOS.
Needs conda-pack (pip install conda-pack).
"""

import argparse
import platform
import re
import shutil
import stat
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
# parts of the repository that go into app/
APP_ITEMS = ("fieldshift", "data", "docs", "LICENSE", "README.md")
# never copied
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pkl", ".DS_Store")


def version():
    text = (ROOT / "fieldshift" / "__init__.py").read_text("utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def platform_name():
    system = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}[platform.system()]
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine,
                                                                                     machine)
    return f"{system}-{arch}"


def pack_runtime(env, target):
    import conda_pack
    print(f"packing {env} -> {target} (conda-pack)", flush=True)
    conda_pack.pack(prefix=str(env), output=str(target), format="no-archive",
                    ignore_missing_files=True, ignore_editable_packages=True, force=True,
                    verbose=False)


def copy_app(target):
    target.mkdir(parents=True)
    for item in APP_ITEMS:
        src = ROOT / item
        if src.is_dir():
            shutil.copytree(src, target / item, ignore=SKIP)
        elif src.exists():
            shutil.copy2(src, target / item)
    build = ROOT / "cpp" / "build"
    libs = [p for p in build.glob("*fieldshift_core*") if p.suffix in (".so", ".dylib", ".dll")] \
        if build.exists() else []
    if libs:                                     # optional C++ core, loaded from cpp/build
        (target / "cpp" / "build").mkdir(parents=True)
        for lib in libs:
            shutil.copy2(lib, target / "cpp" / "build" / lib.name)
    (target / "terrenos").mkdir(exist_ok=True)   # where the user's fields are saved


def add_launcher(folder, system):
    name = {"windows": "FieldShift.bat", "macos": "FieldShift.command",
            "linux": "FieldShift.sh"}[system]
    dest = folder / name
    shutil.copy2(PACKAGING / "launchers" / name, dest)
    if system != "windows":
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        dest.write_bytes(dest.read_bytes().replace(b"\r\n", b"\n"))


def archive(folder, system):
    out = folder.with_name(folder.name + (".zip" if system == "windows" else ".tar.gz"))
    print(f"writing {out}", flush=True)
    if system == "windows":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in sorted(folder.rglob("*")):
                zf.write(path, path.relative_to(folder.parent))
    else:
        with tarfile.open(out, "w:gz", compresslevel=6) as tf:
            tf.add(folder, arcname=folder.name)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", required=True, help="prefix of the conda environment to pack")
    parser.add_argument("--out", default=str(ROOT / "dist"), help="output folder")
    parser.add_argument("--no-archive", action="store_true", help="only build the folder")
    args = parser.parse_args(argv)

    plat = platform_name()
    system = plat.split("-")[0]
    name = f"FieldShift-{version()}-{plat}"
    out = Path(args.out)
    folder = out / name
    if folder.exists():
        shutil.rmtree(folder)
    out.mkdir(parents=True, exist_ok=True)
    pack_runtime(Path(args.env), folder / "runtime")
    copy_app(folder / "app")
    add_launcher(folder, system)
    readme = (PACKAGING / "README-RELEASE.txt").read_text("utf-8")
    (folder / "README-RELEASE.txt").write_text(
        readme.replace("{version}", version()).replace("{platform}", plat), "utf-8")
    if args.no_archive:
        print(folder)
        return 0
    path = archive(folder, system)
    print(f"{path}  {path.stat().st_size / 2**20:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
