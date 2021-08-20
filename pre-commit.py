#!/usr/bin/env python3

from typing import List
import subprocess
import sys
import enum
import argparse
import os


@enum.unique
class Color(enum.Enum):
    RED = "\033[0;31m"
    GREEN = "\033[0;33m"
    CYAN = "\033[0;36m"


NC = "\033[0m"  # No Color


def colorify(
    s: str,
    color: Color,
    no_color: bool = False,
):
    if no_color:
        return s
    return f"{color.value}{s}{NC}"


def rustfmt(fix_inplace: bool = False, no_color: bool = False) -> str:
    cmd = "rustfmt --edition=2018"
    if not fix_inplace:
        cmd += " --check"
    if no_color:
        cmd += " --color=never"
    return cmd


def get_commit_files() -> List[str]:
    files = subprocess.check_output(
        "git diff --cached --name-only --diff-filter=ACM".split()
    )
    return files.decode().splitlines()


def check(
    name: str, suffix: str, cmd: str, changed_files: List[str], no_color: bool = False
):
    print(f"Checking: {name} ", end="")
    applicable_files = list(
        filter(lambda fname: fname.strip().endswith(suffix), changed_files)
    )
    if not applicable_files:
        print(colorify("[NOT APPLICABLE]", Color.CYAN, no_color))
        return

    cmd = f'{cmd} {" ".join(applicable_files)}'
    res = subprocess.run(cmd.split(), capture_output=True)
    if res.returncode != 0:
        print(colorify("[FAILED]", Color.RED, no_color))
        print("Please inspect the output below and run make fmt to fix automatically\n")
        print(res.stdout.decode())
        exit(1)

    print(colorify("[OK]", Color.GREEN, no_color))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fix-inplace", action="store_true", help="apply fixes inplace"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disable colored output", default=not sys.stdout.isatty()
    )
    args = parser.parse_args()

    files = get_commit_files()
    # we use rustfmt here because cargo fmt does not accept list of files
    # it internally gathers project files and feeds them to rustfmt
    # so because we want to check only files included in the commit we use rustfmt directly
    check(
        name="rustfmt",
        suffix=".rs",
        cmd=rustfmt(fix_inplace=args.fix_inplace, no_color=args.no_color),
        changed_files=files,
        no_color=args.no_color,
    )
