"""Lock the version-string contract that the release workflow depends on.

The publish workflow at ``.github/workflows/release.yml`` runs a smoke-install
step that asserts ``ogentic_shield.__version__ == <tag-without-v>``. If the tag
is ``v0.3.0`` but ``src/ogentic_shield/__init__.py`` still has the previous
dev-revision string, the publish step lands on PyPI and *then* the workflow
fails at the smoke check — too late to undo the upload.

This test catches that class of bug at PR time, before the tag is ever pushed.
It pairs with the RELEASING.md discipline of "bump pyproject.toml AND
src/ogentic_shield/__init__.py in the same commit."
"""

from __future__ import annotations

import sys
from pathlib import Path

import ogentic_shield

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - executed on 3.10 only
    import tomli as tomllib  # type: ignore[no-redef,import-not-found]


def test_version_matches_pyproject() -> None:
    """``__version__`` in source must match ``pyproject.toml`` exactly.

    Mirrors the assertion at ``release.yml:121`` so PR-time CI catches a
    mismatch instead of letting it land on PyPI first.
    """
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    expected = pyproject["project"]["version"]
    assert ogentic_shield.__version__ == expected, (
        f"Version mismatch: ogentic_shield.__version__ == "
        f"{ogentic_shield.__version__!r} but pyproject.toml [project].version "
        f"== {expected!r}. Update src/ogentic_shield/__init__.py to match — "
        f"see RELEASING.md."
    )
