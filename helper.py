#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import fnmatch
import os
import shutil
import sys
import xmlrpc.client
import zipfile
import subprocess
import glob
import re
from configparser import ConfigParser
from io import StringIO


def translate():
    """Update translation sources (.ts), force 'Kart' context, and compile (.qm)"""
    print("Updating translation files...")

    # Define paths
    src_dir = os.path.join(os.path.dirname(__file__), "kart")
    i18n_dir = os.path.join(src_dir, "i18n")
    ts_files = glob.glob(os.path.join(i18n_dir, "*.ts"))

    if not ts_files:
        print(f"Error: No .ts files found in {i18n_dir}")
        return

    # Directories to scan for translatable strings
    search_dirs = ["", "gui", "processing", "core"]
    source_files = []
    for d in search_dirs:
        source_files.extend(glob.glob(os.path.join(src_dir, d, "*.py")))

    try:
        # Update .ts files from source code
        if source_files:
            subprocess.run(["pylupdate5", "-noobsolete"] + source_files + ["-ts"] + ts_files, check=True)

        # Compile .ts files into .qm files
        subprocess.run(["lrelease"] + ts_files, check=True)
        print(f"Success: {len(ts_files)} translation files updated.")

    except subprocess.CalledProcessError as e:
        print(f"Error during translation process (Qt Tools): {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def _qgis_pythonpath():
    """Return a PYTHONPATH suitable for running tests against the local QGIS install."""
    entries = ["."]

    if os.name == "nt":
        # Windows: QGIS installs Python alongside the app
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        for qgis_dir in glob.glob(os.path.join(program_files, "QGIS*")):
            entries.append(os.path.join(qgis_dir, "apps", "qgis", "python"))
            entries.append(os.path.join(qgis_dir, "apps", "qgis", "python", "plugins"))
    elif sys.platform == "darwin":
        # macOS: QGIS.app bundle
        entries += [
            "/Applications/QGIS.app/Contents/MacOS/Python",
            "/Applications/QGIS.app/Contents/MacOS/Python/plugins",
        ]
    else:
        # Linux: check Flatpak first, fall back to system install
        flatpak_python = "/app/share/qgis/python"
        if os.path.exists(flatpak_python):
            entries += [flatpak_python, f"{flatpak_python}/plugins"]
        else:
            entries += [
                "/usr/share/qgis/python",
                "/usr/share/qgis/python/plugins",
                "/usr/lib/python3/dist-packages",
            ]

    return os.pathsep.join(entries)


def run_tests(test_path=None):
    """Run the plugin test suite with the correct QGIS PYTHONPATH."""
    test_path = test_path or "kart/tests/test_kartapi.py"

    env = os.environ.copy()
    env["PYTHONPATH"] = _qgis_pythonpath()

    print(f"PYTHONPATH={env['PYTHONPATH']}")
    print(f"Running: python3 -m unittest {test_path} -v\n")

    result = subprocess.run(
        [sys.executable, "-m", "unittest", test_path, "-v"],
        env=env,
    )
    sys.exit(result.returncode)

def package(version=None):
    # Always update translations before packaging
    translate()

    if not version or version.startswith("dev-"):
        # CI uses dev-{SHA}
        archive = "kart.zip"
    else:
        archive = f"kart-{version}.zip"
    print(f"Creating {archive} ...")

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipFile:
        # Exclude development files: .ts are source, .qm are the compiled ones we keep
        excludes = {"test", "tests", "*.pyc", ".git", "metadata.txt", "*.ts"}
        src_dir = os.path.join(os.path.dirname(__file__), "kart")
        exclude = lambda p: any([fnmatch.fnmatch(p, e) for e in excludes])

        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read(os.path.join(src_dir, "metadata.txt"))

        if version:
            cfg.set("general", "version", re.sub(r"^v", "", version))

        buf = StringIO()
        cfg.write(buf)
        zipFile.writestr("kart/metadata.txt", buf.getvalue())
        zipFile.write("LICENSE", "kart/LICENSE")

        def filter_excludes(files):
            if not files:
                return []
            for i in range(len(files) - 1, -1, -1):
                f = files[i]
                if exclude(f):
                    files.remove(f)
            return files

        for root, dirs, files in os.walk(src_dir):
            for f in filter_excludes(files):
                relpath = os.path.relpath(root, ".")
                zipFile.write(os.path.join(root, f), os.path.join(relpath, f))
            filter_excludes(dirs)

    print(f"Build complete: {archive}")


def install(qgis_version):
    src = os.path.join(os.path.dirname(__file__), "kart")

    qgis_folder = f"QGIS{qgis_version}"

    if os.name == "nt":
        default_profile_plugins = (
            f"~/AppData/Roaming/QGIS/{qgis_folder}/profiles/default/python/plugins"
        )
    elif sys.platform == "darwin":
        default_profile_plugins = (
            f"~/Library/Application Support/QGIS/{qgis_folder}"
            "/profiles/default/python/plugins"
        )
    else:
        flatpak_path = os.path.expanduser(
            f"~/.var/app/org.qgis.qgis/data/QGIS/{qgis_folder}/profiles/default/python/plugins")

        if os.path.exists(os.path.dirname(flatpak_path)):
            default_profile_plugins = flatpak_path
        else:
            default_profile_plugins = (
                f"~/.local/share/QGIS/{qgis_folder}/profiles/default/python/plugins"
            )

    dst_plugins = os.path.expanduser(default_profile_plugins)
    os.makedirs(dst_plugins, exist_ok=True)
    dst = os.path.abspath(os.path.join(dst_plugins, "kart"))
    print(f"Installing to {dst} ...")
    src = os.path.abspath(src)
    if os.path.exists(dst):
        try:
            os.remove(dst)
        except IsADirectoryError:
            shutil.rmtree(dst)
    if not hasattr(os, "symlink"):
        shutil.copytree(src, dst)
    elif not os.path.exists(dst):
        os.symlink(src, dst, True)


def publish(archive):
    try:
        creds = os.environ["QGIS_CREDENTIALS"]
    except KeyError:
        print("QGIS_CREDENTIALS not set")
        sys.exit(2)

    url = f"https://{creds}@plugins.qgis.org/plugins/RPC2/"
    conn = xmlrpc.client.ServerProxy(url)
    print(f"Uploading {archive} to https://plugins.qgis.org ...")
    with open(archive, "rb") as fd:
        blob = xmlrpc.client.Binary(fd.read())
    conn.plugin.upload(blob)
    print(f"Upload complete")


def usage():
    print(
        (
            "Usage:\n"
            f"  {sys.argv[0]} install [3|4]          Install in your local QGIS 3 or 4 (default: 3)\n"
            f"  {sys.argv[0]} translate              Update and compile translation files (.ts -> .qm)\n"
            f"  {sys.argv[0]} unittest [TEST_PATH]   Run tests (default:test_kartapi)\n"
            f"  {sys.argv[0]} package [VERSION]      Build a QGIS plugin zip file\n"
            f"  {sys.argv[0]} publish [ARCHIVE]      Upload to QGIS Python Plugins Repository\n"
        ),
        file=sys.stderr,
    )
    sys.exit(2)


if len(sys.argv) >= 2 and sys.argv[1] == "install":
    qgis_ver = sys.argv[2] if len(sys.argv) > 2 else "3"
    install(qgis_ver)
elif len(sys.argv) == 2 and sys.argv[1] == "translate":
    translate()
elif len(sys.argv) in [2, 3] and sys.argv[1] == "unittest":
    run_tests(*sys.argv[2:])
elif len(sys.argv) in [2, 3] and sys.argv[1] == "package":
    package(*sys.argv[2:])
elif len(sys.argv) == 3 and sys.argv[1] == "publish":
    publish(sys.argv[2])
else:
    usage()