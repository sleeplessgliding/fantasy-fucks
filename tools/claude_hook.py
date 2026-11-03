#!/usr/bin/env python3
"""Claude Code PreToolUse hook (wired up in .claude/settings.json).

Before any Bash command that runs `git commit`: if the newest weekly page
(this-season/power-rankings-week-N) has changes, refresh its Sleeper data with
tools/ff.py build N, then run tools/ff.py check N. Problems block the command
(exit 2) and are shown to Claude so it can fix them and try again.
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except ValueError:
    sys.exit(0)
if not re.search(r"\bgit\b[^;&|]*\bcommit\b", cmd):
    sys.exit(0)

sys.path.insert(0, str(ROOT / "tools"))
import ff  # noqa: E402

n = ff.latest_week()
if n is None:
    sys.exit(0)
rel = str(ff.page_path(n).relative_to(ROOT))
git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout
if not git("status", "--porcelain", "--", rel).strip():
    sys.exit(0)  # this commit doesn't touch the newest weekly page

was_staged = rel in git("diff", "--cached", "--name-only").split()
try:
    ff.cmd_build(n)
except SystemExit as e:
    print(f"Blocked: tools/ff.py build {n} failed (see above). Fix the cause; don't bypass this check.", file=sys.stderr)
    sys.exit(2)
if was_staged:
    git("add", rel)
probs = ff.check_problems(n)
if probs:
    print(f"Blocked: week {n} isn't ready to publish. tools/ff.py refreshed the Sleeper data; fix these and commit again:", file=sys.stderr)
    for p in probs:
        print(f"  - {p}", file=sys.stderr)
    print("Never hand-edit the generated sections or bypass this check (no --no-verify, no editing tools/ to pass).", file=sys.stderr)
    sys.exit(2)
print(f"tools/ff.py: week {n} built from Sleeper and passed every check.", file=sys.stderr)
sys.exit(0)
