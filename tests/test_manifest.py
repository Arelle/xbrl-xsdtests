from __future__ import annotations

import json
from pathlib import Path

from xbrl_xsdtests.manifest import (
    MANIFEST_FILENAME,
    SkipManifest,
)
from xbrl_xsdtests.model import ReasonCode, SkipRecord


def _skip(reason: ReasonCode, *, group: str = "g", instance: str | None = None) -> SkipRecord:
    return SkipRecord(
        source="NIST",
        group=group,
        instance=instance,
        reason=reason,
        detail=f"{reason.value} detail",
    )


# A representative mix: two of one reason, one each of two others, one with an instance.
RECORDS = [
    _skip(ReasonCode.UNSUPPORTED_LIST, group="list-1"),
    _skip(ReasonCode.UNSUPPORTED_LIST, group="list-2"),
    _skip(ReasonCode.NO_XBRLI_ITEMTYPE, group="id-1"),
    _skip(ReasonCode.SCHEMA_TEST_ONLY, group="schema-only"),
    _skip(ReasonCode.UNPARSEABLE, group="bad", instance="bad/i-1.xml"),
]


def _manifest() -> SkipManifest:
    manifest = SkipManifest()
    manifest.extend(RECORDS)
    return manifest


class TestSummary:
    def test_total_counts_every_record(self) -> None:
        assert _manifest().summary()["total"] == len(RECORDS)

    def test_counts_by_reason(self) -> None:
        by_reason = _manifest().summary()["by_reason"]
        assert by_reason == {
            "no-xbrli-itemtype": 1,
            "schema-test-only": 1,
            "unparseable": 1,
            "unsupported-list": 2,
        }

    def test_by_reason_sorted(self) -> None:
        by_reason = _manifest().summary()["by_reason"]
        assert list(by_reason) == sorted(by_reason)

    def test_empty_manifest(self) -> None:
        summary = SkipManifest().summary()
        assert summary == {"total": 0, "by_reason": {}}


class TestRecords:
    def test_records_preserve_insertion_order(self) -> None:
        manifest = SkipManifest()
        manifest.add(RECORDS[0])
        manifest.add(RECORDS[2])
        assert manifest.records == (RECORDS[0], RECORDS[2])

    def test_skip_serialization_fields(self) -> None:
        skips = _manifest().to_dict()["skips"]
        assert skips[-1] == {
            "source": "NIST",
            "group": "bad",
            "instance": "bad/i-1.xml",
            "reason": "unparseable",
            "detail": "unparseable detail",
        }
        # Reason codes serialize as their wire string, not the enum repr.
        assert all(isinstance(skip["reason"], str) for skip in skips)
        # Group-level skips carry a null instance.
        assert skips[0]["instance"] is None


class TestWrite:
    def test_writes_valid_json_to_expected_path(self, tmp_path: Path) -> None:
        path = _manifest().write(tmp_path)
        assert path == tmp_path / MANIFEST_FILENAME
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["summary"]["total"] == len(RECORDS)
        assert len(loaded["skips"]) == len(RECORDS)

    def test_write_creates_missing_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "out"
        path = _manifest().write(out)
        assert path.is_file()

    def test_write_is_deterministic(self, tmp_path: Path) -> None:
        first = _manifest().write(tmp_path / "a").read_text(encoding="utf-8")
        second = _manifest().write(tmp_path / "b").read_text(encoding="utf-8")
        assert first == second
        assert first.endswith("\n")
