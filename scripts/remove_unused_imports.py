"""Remove the unused imports that ESLint reports.

The rule reports the *name* and the *line* of the import specifier. This
script re-runs ESLint, collects the unused named imports, and removes them
from the import statements. It never removes a default import or a namespace
import, and it never touches anything that is not an import statement.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def collect_unused() -> dict[str, set[str]]:
    result = subprocess.run(
        ["npx", "eslint", "src", "--format", "json"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if not result.stdout:
        print("eslint produced no output:", result.stderr[:500])
        return {}
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print("could not parse eslint output:", exc)
        return {}

    unused: dict[str, set[str]] = defaultdict(set)
    for file_entry in report:
        path = file_entry["filePath"]
        for message in file_entry.get("messages", []):
            if message.get("ruleId") != "@typescript-eslint/no-unused-vars":
                continue
            match = re.match(r"'([^']+)' is defined but never used", message.get("message", ""))
            if not match:
                continue
            unused[path].add(match.group(1))
    return unused


def strip_named_imports(source: str, names: set[str]) -> str:
    """Remove the given names from the named import lists."""
    out = source
    for name in sorted(names):
        # `import { A, B } from "x"` -> remove `A` (and a trailing comma)
        pattern = re.compile(
            r"(import\s*\{[^}]*?)\b" + re.escape(name) + r"\s*,\s*", re.DOTALL
        )
        new_source, count = pattern.subn(r"\1", out, count=1)
        if count:
            out = new_source
            continue
        # `import { A } from "x"` (single specifier, no trailing comma)
        pattern = re.compile(
            r"import\s*\{\s*" + re.escape(name) + r"\s*\}\s*from\s*[\"'][^\"']+[\"'];?"
        )
        new_source, count = pattern.subn("", out, count=1)
        if count:
            out = new_source
            continue
        # `import Default, { A } from "x"` -> `import Default from "x"`
        pattern = re.compile(
            r"(import\s+[A-Za-z_$][\w$]*\s*,\s*\{[^}]*?)\b" + re.escape(name) + r"\s*,\s*",
            re.DOTALL,
        )
        new_source, count = pattern.subn(r"\1", out, count=1)
        if count:
            out = new_source
    return out


def main() -> int:
    unused = collect_unused()
    if not unused:
        print("no unused imports reported")
        return 0

    changed = 0
    for path, names in unused.items():
        file_path = Path(path)
        if not file_path.exists():
            continue
        source = file_path.read_text(encoding="utf-8")
        updated = strip_named_imports(source, names)
        if updated != source:
            file_path.write_text(updated, encoding="utf-8", newline="")
            changed += 1
            print(f"cleaned {file_path.relative_to(FRONTEND)}: {', '.join(sorted(names))}")

    print(f"\n{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
