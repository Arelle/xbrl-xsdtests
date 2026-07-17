"""
See COPYRIGHT.md for copyright information.

SkipManifest writer (``skip-manifest.json``).

Every in-scope testGroup/instance that is NOT translated to an XBRL fact is
recorded as a ``SkipRecord`` (with a machine-readable ``ReasonCode``). The
manifest is written on every run as a full account of what was left out, so a
reviewer can audit coverage and triage by reason. The JSON carries a ``summary``
(total + counts per reason code, both deterministic) followed by the ``skips``
array in stream/insertion order.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from xbrl_xsdtests.model import SkipRecord

MANIFEST_FILENAME = "skip-manifest.json"


class SkipManifest:
    """Collects ``SkipRecord``s and serializes them to ``skip-manifest.json``."""

    def __init__(self) -> None:
        self._records: list[SkipRecord] = []

    def add(self, record: SkipRecord) -> None:
        self._records.append(record)

    def extend(self, records: Iterable[SkipRecord]) -> None:
        self._records.extend(records)

    @property
    def records(self) -> tuple[SkipRecord, ...]:
        return tuple(self._records)

    def summary(self) -> dict[str, Any]:
        """Total count plus per-reason counts, sorted by reason code for stability."""
        counts = Counter(record.reason.value for record in self._records)
        return {
            "total": len(self._records),
            "by_reason": {reason: counts[reason] for reason in sorted(counts)},
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "skips": [self._record_to_dict(record) for record in self._records],
        }

    def write(self, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        path = out / MANIFEST_FILENAME
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _record_to_dict(record: SkipRecord) -> dict[str, Any]:
        return {
            "source": record.source,
            "group": record.group,
            "instance": record.instance,
            "reason": record.reason.value,
            "detail": record.detail,
        }
