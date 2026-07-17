"""
See COPYRIGHT.md for copyright information.

SourceSelector: the fixed in-scope XSTS testSet members and their version tags.

Only XSD 1.0 datatype sources from NIST + Microsoft + Sun are listed for v1.
The 1.1-only contributors (IBM/Saxon/Oracle/WG/extra-suite) are intentionally
absent; ``xsd_version`` is a first-class dimension so they can be added later
without restructuring.

Gotcha: the Microsoft sets use a ``.xml`` extension, not ``.testSet``.
"""

from __future__ import annotations

from pathlib import Path

from xbrl_xsdtests.model import SourceSet

# Default data root: current working directory (the repo root when run normally).
DEFAULT_ROOT = Path.cwd()


# (repo-relative member path, contributor) — XSD 1.0 datatype sources only.
_IN_SCOPE: tuple[tuple[str, str], ...] = (
    ("nistMeta/NISTXMLSchemaDatatypes.testSet", "NIST"),
    ("msMeta/Regex_w3c.xml", "Microsoft"),
    ("msMeta/DataTypes_w3c.xml", "Microsoft"),
    ("msMeta/SimpleType_w3c.xml", "Microsoft"),
    ("sunMeta/SType.testSet", "Sun"),
)


def in_scope_sources() -> list[SourceSet]:
    """Return the fixed list of in-scope XSTS source sets (XSD 1.0)."""
    return [
        SourceSet(member=relative_path, contributor=contributor, xsd_version="1.0")
        for relative_path, contributor in _IN_SCOPE
    ]
