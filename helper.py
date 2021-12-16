#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import fnmatch
import os
import re
import shutil
import sys
import zipfile
from configparser import ConfigParser
from io import StringIO


def package(version=None):
    archive = f"kart-{version}.zip" if version else "kart.zip"
    print(f"Creating {archive} ...")

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipFile:
        excludes = {"test", "tests", "*.pyc", ".git", "metadata.txt"}
        src_dir = os.path.join(os.path.dirname(__file__), "kart")
        exclude = lambda p: any([fnmatch.fnmatch(p, e) for e in excludes])

        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read(os.path.join(src_dir, "metadata.txt"))

        if version:
            cfg.set("general", "version", re.sub(r'^v', '', version))

        buf = StringIO()
        cfg.write(buf)
        zipFile.writestr("kart/metadata.txt", buf.getvalue())

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


def install():
    src = os.path.join(os.path.dirname(__file__), "kart")
    if os.name == "nt":
        default_profile_plugins = (
            "~/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins"
        )
    elif sys.platform == "darwin":
        default_profile_plugins = (
            "~/Library/Application Support/QGIS/QGIS3"
            "/profiles/default/python/plugins"
        )
    else:
        default_profile_plugins = (
            "~/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
        )

    dst_plugins = os.path.expanduser(default_profile_plugins)
    os.makedirs(dst_plugins, exist_ok=True)
    dst = os.path.abspath(os.path.join(dst_plugins, "kart"))
    src = os.path.abspath(src)
    shutil.rmtree(dst)
    if not hasattr(os, "symlink"):
        shutil.copytree(src, dst)
    elif not os.path.exists(dst):
        os.symlink(src, dst, True)


def usage():
    print((
        "Usage:\n"
        f"  {sys.argv[0]} package [VERSION]    Build a QGIS plugin zip file\n"
        f"  {sys.argv[0]} install              Install in your local QGIS (for development)\n"
    ), file=sys.stderr)
    sys.exit(2)

if len(sys.argv) == 2 and sys.argv[1] == "install":
    install()
elif len(sys.argv) in [2, 3] and sys.argv[1] == "package":
    package(*sys.argv[2:])
else:
    usage()
