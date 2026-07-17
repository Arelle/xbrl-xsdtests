from __future__ import annotations

from pathlib import Path

import pytest
from xbrl_xsdtests import xmlutil as etree

from conftest import REPO_ROOT
from xbrl_xsdtests import generate, sources
from xbrl_xsdtests.emit import INDEX_FILENAME
from xbrl_xsdtests.generate import (
    ConsistencyError,
    GenerateResult,
)
from xbrl_xsdtests.manifest import MANIFEST_FILENAME

_LIMIT = 20


@pytest.fixture(scope="module")
def suite(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, GenerateResult]:
    out = tmp_path_factory.mktemp("suite")
    result = generate.generate(root=REPO_ROOT, out=out, limit=_LIMIT, self_test=True)
    return out, result


class TestLimitedRun:
    def test_processes_exactly_limit_groups(self, suite: tuple[Path, GenerateResult]) -> None:
        _out, result = suite
        assert result.groups == _LIMIT

    def test_emits_taxonomies_instances_and_testcases(self, suite: tuple[Path, GenerateResult]) -> None:
        out, result = suite
        assert result.taxonomies >= 1
        assert result.instances >= 1
        assert result.testcases >= 1
        assert len(list((out / "taxonomies").glob("gen-*.xsd"))) == result.taxonomies
        assert len(list(out.rglob("*.xbrl"))) == result.instances

    def test_writes_index_and_manifest(self, suite: tuple[Path, GenerateResult]) -> None:
        out, result = suite
        assert (out / INDEX_FILENAME).is_file()
        assert (out / MANIFEST_FILENAME).is_file()
        assert result.index_path == out / INDEX_FILENAME
        assert result.manifest_path == out / MANIFEST_FILENAME

    def test_index_lists_every_emitted_testcase(self, suite: tuple[Path, GenerateResult]) -> None:
        out, result = suite
        index = etree.parse(str(out / INDEX_FILENAME)).getroot()
        uris = [tc.get("uri") for tc in index.findall("{*}testcase")]
        assert len(uris) == result.testcases
        assert all((out / uri).is_file() for uri in uris)


class TestConsistencyCheck:
    def test_passes_on_freshly_generated_suite(self, tmp_path: Path) -> None:
        generate.generate(root=REPO_ROOT, out=tmp_path, limit=5, self_test=False)
        generate.check_consistency(tmp_path)  # must not raise

    def test_fails_when_instance_removed(self, tmp_path: Path) -> None:
        generate.generate(root=REPO_ROOT, out=tmp_path, limit=5, self_test=False)
        instance = next(tmp_path.rglob("*.xbrl"))
        instance.unlink()
        with pytest.raises(ConsistencyError, match="missing instance file"):
            generate.check_consistency(tmp_path)

    def test_fails_when_taxonomy_removed(self, tmp_path: Path) -> None:
        generate.generate(root=REPO_ROOT, out=tmp_path, limit=5, self_test=False)
        taxonomy = next((tmp_path / "taxonomies").glob("gen-*.xsd"))
        taxonomy.unlink()
        with pytest.raises(ConsistencyError, match="missing taxonomy file"):
            generate.check_consistency(tmp_path)

    def test_fails_when_testcase_removed(self, tmp_path: Path) -> None:
        generate.generate(root=REPO_ROOT, out=tmp_path, limit=5, self_test=False)
        testcase = next(tmp_path.rglob("*-testcase.xml"))
        testcase.unlink()
        with pytest.raises(ConsistencyError, match="missing testcase file"):
            generate.check_consistency(tmp_path)

    def test_self_test_raises_during_generate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import xbrl_xsdtests.generate as gen

        def _boom(_out: Path) -> None:
            raise ConsistencyError("forced")

        monkeypatch.setattr(gen, "check_consistency", _boom)
        with pytest.raises(ConsistencyError, match="forced"):
            gen.generate(root=REPO_ROOT, out=tmp_path, limit=5, self_test=True)


class TestVersionSelection:
    def test_unknown_version_emits_empty_suite(self, tmp_path: Path) -> None:
        result = generate.generate(root=REPO_ROOT, out=tmp_path, version="1.1", limit=None, self_test=True)
        assert result.groups == 0
        assert result.taxonomies == 0
        assert result.instances == 0
        index = etree.parse(str(tmp_path / INDEX_FILENAME)).getroot()
        assert index.findall("{*}testcase") == []


class TestOffline:
    def test_default_root_exists(self) -> None:
        assert REPO_ROOT.is_dir()
