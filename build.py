# -*- coding: utf-8 -*-

import os
import fnmatch
import zipfile
import subprocess


def package():
    package_file = "./krt.zip"
    with zipfile.ZipFile(package_file, "w", zipfile.ZIP_DEFLATED) as f:
        make_zip(f)


def make_zip(zipFile):
    print("Creating zip...")
    excludes = {"test", "tests", '*.pyc', ".git", "metadata.txt"}
    src_dir = os.path.dir(os.path.dirname(__file__), "kart")
    exclude = lambda p: any([fnmatch.fnmatch(p, e) for e in excludes])

    metadata_file = os.path.join(src_dir, "metadata.txt")
    cfg = SafeConfigParser()
    cfg.optionxform = str
    cfg.read(metadata_file)
    base_version = cfg.get('general', 'version')
    head_path = path('.git/HEAD')
    head_ref = head_path.open('rU').readline().strip()[5:]
    ref_file = path(".git/" + head_ref)
    ref = ref_file.open('rU').readline().strip()
    cfg.set("general", "version", f"{base_version}-{ref}")

    buf = StringIO()
    cfg.write(buf)
    zipFile.writestr(os.path.join(src_dir, "kart", "metadata.txt"), buf.getvalue())

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
