#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import fnmatch
import zipfile
from configparser import ConfigParser
from io import StringIO


def package():
    print("Creating zip...")
    with zipfile.ZipFile("./kart.zip", "w", zipfile.ZIP_DEFLATED) as zipFile:
        excludes = {"test", "tests", "*.pyc", ".git", "metadata.txt"}
        src_dir = os.path.join(os.path.dirname(__file__), "kart")
        exclude = lambda p: any([fnmatch.fnmatch(p, e) for e in excludes])

        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read(os.path.join(src_dir, "metadata.txt"))
        try:
            version = sys.argv[2]
        except IndexError:
            version = cfg.get("general", "version")
        if version.startswith("v"):
            version = version[1:]
        cfg.set("general", "version", version)
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
    print("Usage: python helper.py install|package")


if sys.argv[1] == "install" and len(sys.argv) == 2:
    install()
elif sys.argv[1] == "package" and len(sys.argv) in [2, 3]:
    package()
else:
    usage()
    sys.exit(2)
