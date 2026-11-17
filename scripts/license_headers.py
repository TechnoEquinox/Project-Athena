#!/usr/bin/env python3
"""Add, or check for, a two-line license header on the project's source files.

    python3 scripts/license_headers.py --holder "Connor Bailey"   # add missing headers
    python3 scripts/license_headers.py --check                    # list files without one
"""
import argparse
import subprocess
import sys
from pathlib import Path

# (prefix, suffix) wrapped around each header line
STYLES = {
    ".py": ("# ", ""), ".sh": ("# ", ""), ".yml": ("# ", ""), ".yaml": ("# ", ""),
    ".js": ("// ", ""), ".mjs": ("// ", ""), ".css": ("/* ", " */"),
    ".sql": ("-- ", ""), ".vue": ("<!-- ", " -->"),
}
BY_NAME = {"Dockerfile": ("# ", ""), "Caddyfile": ("# ", "")}
KEEP_FIRST = ("#!", "# syntax=")   # these lines must stay first in the file


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True, text=True
    ).stdout
    return [Path(p) for p in out.split("\0") if p]


def comment_style(path):
    return BY_NAME.get(path.name) or STYLES.get(path.suffix)


def has_header(lines):
    return any("SPDX-License-Identifier" in line for line in lines[:6])


def with_header(text, style, spdx, holder, year):
    prefix, suffix = style
    header = [
        f"{prefix}SPDX-License-Identifier: {spdx}{suffix}",
        f"{prefix}Copyright (C) {year} {holder}{suffix}",
    ]
    lines = text.split("\n")
    keep = 1 if lines and lines[0].startswith(KEEP_FIRST) else 0
    rest = lines[keep:]
    spacer = [""] if rest and rest[0] != "" else []
    return "\n".join(lines[:keep] + header + spacer + rest)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only list files that lack a header")
    parser.add_argument("--spdx", default="AGPL-3.0-or-later")
    parser.add_argument("--holder", help="copyright holder, for example 'Connor Bailey'")
    parser.add_argument("--year", default="2026")
    args = parser.parse_args()
    if not args.check and not args.holder:
        parser.error("--holder is required when adding headers")

    missing = []
    for path in tracked_files():
        style = comment_style(path)
        if style is None or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if has_header(text.split("\n")):
            continue
        missing.append(path)
        if not args.check:
            path.write_text(with_header(text, style, args.spdx, args.holder, args.year), encoding="utf-8")

    verb = "Missing a header" if args.check else "Added a header to"
    for path in missing:
        print(f"{verb}: {path}")
    print(f"{len(missing)} file(s).")
    return 1 if (args.check and missing) else 0


if __name__ == "__main__":
    sys.exit(main())