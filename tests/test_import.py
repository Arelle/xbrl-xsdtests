from __future__ import annotations

import subprocess
import sys

PACKAGE = "xbrl_xsdtests"
SUBMODULES = (
    "__main__",
    "typemap",
    "model",
    "sources",
    "parse",
    "dedup",
    "emit",
    "manifest",
    "generate",
)
# The generator must not import arelle at all (it's a dev-only dependency).
FORBIDDEN_MODULES = ("arelle", "arelle.XbrlConst", "arelle.ModelXbrl", "arelle.Cntlr")


def test_package_and_submodules_import_cleanly() -> None:
    imports = "; ".join(f"import {PACKAGE}.{m}" for m in SUBMODULES)
    subprocess.run([sys.executable, "-c", f"import {PACKAGE}; {imports}"], check=True)


def test_importing_package_does_not_load_arelle() -> None:
    code = (
        "import sys; "
        f"import {PACKAGE}.typemap, {PACKAGE}.model, {PACKAGE}.generate; "
        f"loaded = [m for m in {FORBIDDEN_MODULES!r} if m in sys.modules]; "
        "assert not loaded, f'Arelle imported: {loaded}'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_main_prints_usage() -> None:
    result = subprocess.run(
        [sys.executable, "-m", PACKAGE, "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "usage:" in result.stdout
