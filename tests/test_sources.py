from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REPO_ROOT
from xbrl_xsdtests import sources
from xbrl_xsdtests.model import SourceSet

# 1.1-only contributors that must NOT appear in the v1 selection.
DEFERRED_MARKERS = ("ibmMeta/", "saxonMeta/", "oracleMeta/", "wgMeta/", "extra-suite")


class TestInScopeSources:
    def test_returns_source_sets(self) -> None:
        result = sources.in_scope_sources()
        assert result
        assert all(isinstance(s, SourceSet) for s in result)

    def test_expected_member_count(self) -> None:
        # NIST x1 + Microsoft x3 + Sun x1
        assert len(sources.in_scope_sources()) == 5

    def test_all_tagged_xsd_1_0(self) -> None:
        assert all(s.xsd_version == "1.0" for s in sources.in_scope_sources())

    def test_contributor_breakdown(self) -> None:
        by_contributor: dict[str, int] = {}
        for s in sources.in_scope_sources():
            by_contributor[s.contributor] = by_contributor.get(s.contributor, 0) + 1
        assert by_contributor == {"NIST": 1, "Microsoft": 3, "Sun": 1}

    def test_microsoft_members_use_xml_extension(self) -> None:
        ms = [s for s in sources.in_scope_sources() if s.contributor == "Microsoft"]
        assert ms
        assert all(s.member.endswith(".xml") for s in ms)

    def test_no_deferred_1_1_sources(self) -> None:
        for s in sources.in_scope_sources():
            assert not any(marker in s.member for marker in DEFERRED_MARKERS)

    def test_members_are_unique(self) -> None:
        members = [s.member for s in sources.in_scope_sources()]
        assert len(members) == len(set(members))


class TestMembersResolveOnDisk:
    def test_root_exists(self) -> None:
        assert REPO_ROOT.is_dir()

    def test_every_member_present_on_disk(self) -> None:
        for s in sources.in_scope_sources():
            assert (REPO_ROOT / s.member).is_file(), f"missing: {s.member}"
