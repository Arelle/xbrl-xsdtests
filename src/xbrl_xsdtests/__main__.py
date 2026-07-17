"""
See COPYRIGHT.md for copyright information.

CLI entry point for the XSTS value/facet conformance generator. Streams the
in-scope XSTS datatype tests from the committed test data directories and emits
an XBRL-flavored conformance suite (taxonomies + instances + native index) plus
a skip manifest, then runs the internal consistency check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xbrl_xsdtests import sources
from xbrl_xsdtests.model import InstanceTestRef
from xbrl_xsdtests.parse import TestSetParser

_DEFAULT_OUT = "output"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m xbrl_xsdtests",
        description=(
            "Generate an XBRL-flavored conformance suite from the W3C XML Schema "
            "Test Suite (XSTS) datatype tests."
        ),
    )
    parser.add_argument("--data-root", type=str, default=".", help="Root directory containing XSTS test data (default: cwd)")
    parser.add_argument("--out", type=str, default=_DEFAULT_OUT, help="Output directory")
    parser.add_argument("--version", type=str, default="1.0", help="XSD outcome version")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N testGroups")
    parser.add_argument("--no-self-test", action="store_true", help="Skip the internal consistency check")
    parser.add_argument("--list-sources", action="store_true", help="List in-scope testSet members and exit")
    parser.add_argument("--count", action="store_true", help="Print per-source instanceTest counts and exit")
    return parser


def _list_sources() -> int:
    in_scope = sources.in_scope_sources()
    by_contributor: dict[str, int] = {}
    for s in in_scope:
        by_contributor[s.contributor] = by_contributor.get(s.contributor, 0) + 1
    sys.stdout.write("In-scope XSTS sources (XSD 1.0):\n")
    for s in in_scope:
        sys.stdout.write(f"  [{s.contributor:<9}] {s.member}\n")
    breakdown = ", ".join(f"{c}={n}" for c, n in sorted(by_contributor.items()))
    sys.stdout.write(f"\n{len(in_scope)} sources ({breakdown})\n")
    return 0


def _count(root: Path) -> int:
    total = 0
    parser = TestSetParser(root)
    sys.stdout.write("instanceTest counts per source:\n")
    for source in sources.in_scope_sources():
        n = sum(1 for r in parser.iter_instance_tests(source) if isinstance(r, InstanceTestRef))
        total += n
        sys.stdout.write(f"  {n:7}  {source.member}\n")
    sys.stdout.write(f"\n{total} instanceTests total\n")
    return 0


def _generate(args: argparse.Namespace) -> int:
    from xbrl_xsdtests import generate

    result = generate.generate(
        root=Path(args.data_root),
        out=args.out,
        version=args.version,
        limit=args.limit,
        self_test=not args.no_self_test,
    )
    sys.stdout.write(f"Generated suite at {result.out}\n")
    sys.stdout.write(
        f"  testGroups processed : {result.groups}\n"
        f"  taxonomies           : {result.taxonomies}\n"
        f"  instances            : {result.instances}\n"
        f"  testcases            : {result.testcases}\n"
        f"  skips                : {result.skips}\n"
    )
    for reason, count in result.skips_by_reason.items():
        sys.stdout.write(f"      {reason:<20} {count}\n")
    sys.stdout.write(f"  index                : {result.index_path}\n")
    sys.stdout.write(f"  manifest             : {result.manifest_path}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.list_sources:
        return _list_sources()
    if args.count:
        return _count(Path(args.data_root))
    return _generate(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
