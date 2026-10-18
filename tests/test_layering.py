"""Standing check: the three shell-out/outbound-call boundaries hold package-wide.

Only `omp_client.py` may import `subprocess` (it shells out to `omp`); only
`gist_publish.py` may import `subprocess` for `gh`; only
`providers/pollinations.py` may import `requests`, the one module allowed to
make outbound HTTP calls to an image-generation provider. This scans every
module in `src/cosplay`, not just the two or three expected to use them, so
a new module that starts shelling out or calling HTTP directly fails this
check immediately rather than silently crossing the boundary.
"""

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "cosplay"

_ALLOWED_SUBPROCESS_MODULES = {"omp_client.py", "gist_publish.py"}
_ALLOWED_REQUESTS_MODULES = {"pollinations.py"}


def _imported_top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _all_source_files() -> list[Path]:
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def test_only_omp_client_and_gist_publish_import_subprocess():
    offenders = [
        f.relative_to(_PACKAGE_ROOT)
        for f in _all_source_files()
        if "subprocess" in _imported_top_level_names(f)
        and f.name not in _ALLOWED_SUBPROCESS_MODULES
    ]
    assert offenders == [], f"unexpected subprocess import(s): {offenders}"


def test_only_pollinations_provider_imports_requests():
    offenders = [
        f.relative_to(_PACKAGE_ROOT)
        for f in _all_source_files()
        if "requests" in _imported_top_level_names(f) and f.name not in _ALLOWED_REQUESTS_MODULES
    ]
    assert offenders == [], f"unexpected requests import(s): {offenders}"


def test_omp_client_actually_imports_subprocess():
    """Sanity: the allow-list isn't vacuously satisfied by nobody importing it."""
    assert "subprocess" in _imported_top_level_names(_PACKAGE_ROOT / "omp_client.py")


def test_gist_publish_actually_imports_subprocess():
    assert "subprocess" in _imported_top_level_names(_PACKAGE_ROOT / "gist_publish.py")


def test_pollinations_provider_actually_imports_requests():
    assert "requests" in _imported_top_level_names(_PACKAGE_ROOT / "providers" / "pollinations.py")
