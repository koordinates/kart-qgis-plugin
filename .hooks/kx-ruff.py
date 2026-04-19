#!/usr/bin/env python3
import subprocess
import sys

filez = sys.argv[1:]

print("Running ruff linter")
subprocess.check_call(["ruff", "check", "--fix", "--force-exclude", *filez])

print("Running ruff formatter")
subprocess.check_call(["ruff", "format", "--force-exclude", *filez])

# pre-commit doesn't add changed files to the index. Normally changed files fail the hook.
# however, just calling git add sneakily works around that.
subprocess.check_call(["git", "add"] + filez)
