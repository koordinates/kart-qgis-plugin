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

# QGIS Docker image tags
QGIS_TEST_VERSION = "latest"
QGIS_MINIMUM_VERSION = "release-3_34"  # qgisMinimumVersion=3.16
QGIS_MAXIMUM_VERSION = "stable-questing"  # qgisMaximumVersion=4.99
KART_VERSION = "0.15.3"


def translate(locale=None):
    """
    Update translation sources (.ts) and compile them to .qm files.

    :param locale: Locale to update and compile (e.g., 'en', 'pt_BR'). If not specified, all locales are processed.
    """

    print("Updating translation files...")

    # Define paths
    src_dir = os.path.join(os.path.dirname(__file__), "kart")
    i18n_dir = os.path.join(src_dir, "i18n")

    if locale:
        ts_files = glob.glob(os.path.join(i18n_dir, f"kart_{locale}.ts"))
        if not ts_files:
            print(f"Error: No .ts file found for locale '{locale}' in {i18n_dir}")
            return
    else:
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

    except FileNotFoundError as e:
        print(f"Error: '{e.filename}' not found. Please install it before running this command.")
    except subprocess.CalledProcessError as e:
        print(f"Error during translation process (Qt Tools): {e}")


def run_tests(qgis_version=QGIS_TEST_VERSION, *pytest_args):
    """
        Run the test suite inside the QGIS Docker container.

        :param qgis_version: Docker tag (e.g., 'latest', 'all', 'release-3_34')
        :param pytest_args: Additional arguments forwarded directly to the pytest command.

        Examples:
          python helper.py pytest                          # Run with default version (defined in QGIS_TEST_VERSION)
          python helper.py pytest release-3_34             # Run a specific version
          python helper.py pytest all                      # Run the qgisMinimumVersion and qgisMaximumVersion
          python helper.py pytest latest -k test_clone -vv # Run specific tests and pass extra pytest arguments
    """

    versions = [QGIS_MINIMUM_VERSION, QGIS_MAXIMUM_VERSION] if qgis_version == "all" else [qgis_version]

    for version in versions:
        env = {
            **os.environ,
            "QGIS_TEST_VERSION": version,
            "KART_VERSION": KART_VERSION,
            "GITHUB_WORKSPACE": os.path.abspath(os.path.dirname(__file__)),
        }
        print(f"Running tests in Docker (QGIS_TEST_VERSION={version}) ...")
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                ".docker/docker-compose.gh.yml",
                "run",
                "--build",
                "--rm",
                "qgis",
                "/usr/src/.docker/run-docker-tests.sh",
            ]
            + list(pytest_args),
            env=env,
        )
        if result.returncode != 0:
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
            f"  {sys.argv[0]} install [3|4]                        Install in your local QGIS 3 or 4 (default: 3)\n"
            f"  {sys.argv[0]} translate [LOCALE]                   Update and compile translation files (.ts -> .qm)\n"
            f"  {sys.argv[0]} pytest [QGIS_VERSION] [PYTEST_ARGS]  Run tests in Docker (default: latest, all, docker tag)\n"
            f"  {sys.argv[0]} package [VERSION]                    Build a QGIS plugin zip file\n"
            f"  {sys.argv[0]} publish [ARCHIVE]                    Upload to QGIS Python Plugins Repository\n"
        ),
        file=sys.stderr,
    )
    sys.exit(2)


if len(sys.argv) >= 2 and sys.argv[1] == "install":
    qgis_ver = sys.argv[2] if len(sys.argv) > 2 else "3"
    install(qgis_ver)
elif len(sys.argv) in [2, 3] and sys.argv[1] == "translate":
    translate(*sys.argv[2:])
elif len(sys.argv) >= 2 and sys.argv[1] == "pytest":
    run_tests(*sys.argv[2:])
elif len(sys.argv) in [2, 3] and sys.argv[1] == "package":
    package(*sys.argv[2:])
elif len(sys.argv) == 3 and sys.argv[1] == "publish":
    publish(sys.argv[2])
else:
    usage()
