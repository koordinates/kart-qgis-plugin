# -*- coding: utf-8 -*-

import os
import fnmatch
import zipfile
import subprocess


def package():
    package_file = "./detektia.zip"
    with zipfile.ZipFile(package_file, "w", zipfile.ZIP_DEFLATED) as f:
        make_zip(f)


def make_zip(zipFile):
    print("Creating zip...")
    excludes = {"test", "tests", '*.pyc', ".git"}
    src_dir = "./detektia"
    exclude = lambda p: any([fnmatch.fnmatch(p, e) for e in excludes])

    def filter_excludes(files):
        if not files: return []
        # to prevent descending into dirs, modify the list in place
        for i in range(len(files) - 1, -1, -1):
            f = files[i]
            if exclude(f):
                files.remove(f)
        return files

    for root, dirs, files in os.walk(src_dir):
        for f in filter_excludes(files):
            relpath = os.path.relpath(root, '.')
            zipFile.write(os.path.join(root, f), os.path.join(relpath, f))
        filter_excludes(dirs)


def sh(commands):
    if isinstance(commands, str):
        commands = commands.split(" ")
    out = subprocess.Popen(commands, stdout=subprocess.PIPE)
    stdout, stderr = out.communicate()
    return stdout.decode("utf-8")


package()
