"""Remove the unused local bindings that ESLint reports.

Only bindings that are clearly dead (``const router = useRouter()`` and
similar) are removed. The script re-runs ESLint, groups the reported names
per file, and deletes the matching ``const <name> = ...;`` statement when the
name is not referenced anywhere else in the file.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

# Only these names are safe to remove: they are hook results that are simply
# not used in the component any more.
CANDIDATES = {
    "router",
    "loading",
    "setLoading",
    "user",
    "theme",
}


def collect_unused() -> dict[str, set[str]]:
    result = subprocess.run(
        ["npx", "eslint", "src", "--format", "json"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if not result.stdout:
        return {}
    report = json.loads(result.stdout)

    unused: dict[str, set[str]] = defaultdict(set)
    for file_entry in report:
        for message in file_entry.get("messages", []):
            if message.get("ruleId") != "@typescript-eslint/no-unused-vars":
                continue
            match = re.match(r"'([^']+)' is assigned a value but never used", message.get("message", ""))
            if not match:
                continue
            name = match.group(1)
            if name in CANDIDATES:
                unused[file_entry["filePath"]].add(name)
    return unused


def remove_bindings(source: str, names: set[str]) -> str:
    out = source
    for name in sorted(names):
        # `const router = useRouter();`
        pattern = re.compile(r"^[ \t]*const\s+" + re.escape(name) + r"\s*=\s*useRouter\(\);\s*$\n?", re.M)
        new_source, count = pattern.subn("", out, count=1)
        if count:
            out = new_source
            continue
        # `const loading = ...;` / `const setLoading = ...;`
        pattern = re.compile(
            r"^[ \t]*const\s+(?:" + re.escape(name) + r")\s*=\s*[^;\n]+;\s*$\n?", re.M
        )
        new_source, count = pattern.subn("", out, count=1)
        if count:
            out = new_source
    return out


def main() -> int:
    unused = collect_unused()
    if not unused:
        print("no unused local bindings reported")
        return 0

    changed = 0
    for path, names in unused.items():
        file_path = Path(path)
        if not file_path.exists():
            continue
        source = file_path.read_text(encoding="utf-8")
        updated = remove_bindings(source, names)
        if updated != source:
            file_path.write_text(updated, encoding="utf-8", newline="")
            changed += 1
            print(f"cleaned {file_path.relative_to(FRONTEND)}: {', '.join(sorted(names))}")

    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
