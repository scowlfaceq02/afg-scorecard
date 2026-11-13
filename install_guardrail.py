"""
install_guardrail.py -- installs the git pre-commit hook (November 12th, 2026)
Run once from C:\\Users\\qwhit\\AFG\\ :   python3 install_guardrail.py
After this, ANY git commit that includes docs/index.html (even a manual one)
first runs audit_published.py and is REFUSED if the page fails the audit.
"""
import os, stat, sys
if not os.path.isdir(".git"):
    sys.exit("No .git folder here -- run from C:\\Users\\qwhit\\AFG\\")
for need in ("audit_published.py", "afg_scorecard.db"):
    if not os.path.exists(need):
        sys.exit(f"{need} not found in this folder.")
hook = os.path.join(".git", "hooks", "pre-commit")
body = '#!/bin/sh\nPY=python3\ncommand -v python3 >/dev/null 2>&1 || PY=python\n$PY audit_published.py --hook\nexit $?\n'
open(hook, "w", newline="\n").write(body)
os.chmod(hook, os.stat(hook).st_mode | stat.S_IEXEC)
print("Installed:", hook)
print("Any commit that changes docs/index.html now runs the publication audit first.")
print("To bypass in a true emergency: git commit --no-verify (do not).")
