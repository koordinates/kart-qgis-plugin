# -*- coding: utf-8 -*-

import os
import sys
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
            version = sys.argv[1]
        except IndexError:
            version = cfg.get("general", "version")
        version = "".join(c for c in version if c.isdigit() or c == ".")
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


package()
