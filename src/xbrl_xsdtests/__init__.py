"""
See COPYRIGHT.md for copyright information.

Standalone generator that consumes the W3C XML Schema Test Suite (XSTS) datatype
tests and emits an XBRL-flavored conformance suite.

Import-light by design: only the Python standard library is required at runtime. Arelle is a dev/test
dependency used only by the validation smoke test (``tests/test_smoke.py``).
"""

from __future__ import annotations
