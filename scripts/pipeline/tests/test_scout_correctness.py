"""Correctness test for extract_api_surface() — RC-4b.

Verifies that a regular Python class with public methods, a @property, and
a private method is extracted correctly through the full tree-sitter pipeline.

Coverage gap addressed: existing tests exercise dataclass property extraction
and low-level helpers but do not call extract_api_surface() end-to-end on a
simple class with regular methods.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# sys.path is set by tests/conftest.py — no manual insert needed here.
import scout

from extraction.api_surface import extract_api_surface


# ---------------------------------------------------------------------------
# Minimal Python source fixture (inline — no on-disk fixture files needed)
# ---------------------------------------------------------------------------

_PY_SOURCE = """\
class SimpleDocument:
    \"\"\"A simple document class used as a scout extraction fixture.\"\"\"

    @property
    def title(self) -> str:
        \"\"\"Return the document title.\"\"\"
        return self._title

    def open(self, filename: str) -> None:
        \"\"\"Open a file.\"\"\"
        pass

    def save(self, filename: str) -> None:
        \"\"\"Save a file.\"\"\"
        pass

    def _internal(self) -> None:
        \"\"\"Private helper — must NOT appear in api_surface output.\"\"\"
        pass
"""


def _run_extraction() -> dict[str, dict]:
    """Run extract_api_surface on the inline fixture and return a name→class map."""
    parser = scout.get_parser("python")
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg = Path(tmpdir) / "aspose" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "document.py").write_text(_PY_SOURCE, encoding="utf-8")
        classes, _, _, _, _ = extract_api_surface(
            parser, "python", pkg, Path(tmpdir), "test"
        )
    return {c["name"]: c for c in classes if c.get("kind") == "class_definition"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestApiSurfaceExtractionCorrectness:
    """extract_api_surface() must correctly extract a simple Python class."""

    def test_class_extracted(self):
        """SimpleDocument must appear in the extracted classes."""
        classes = _run_extraction()
        assert "SimpleDocument" in classes, (
            f"Expected 'SimpleDocument' in extracted classes, got: {list(classes)}"
        )

    def test_public_method_open_extracted(self):
        """Public method 'open' must appear in SimpleDocument's methods."""
        classes = _run_extraction()
        methods = [m["name"] for m in classes["SimpleDocument"].get("methods", [])]
        assert "open" in methods, (
            f"Expected 'open' in methods, got: {methods}"
        )

    def test_public_method_save_extracted(self):
        """Public method 'save' must appear in SimpleDocument's methods."""
        classes = _run_extraction()
        methods = [m["name"] for m in classes["SimpleDocument"].get("methods", [])]
        assert "save" in methods, (
            f"Expected 'save' in methods, got: {methods}"
        )

    def test_property_title_extracted(self):
        """@property 'title' must appear in SimpleDocument's properties."""
        classes = _run_extraction()
        props = [p["name"] for p in classes["SimpleDocument"].get("properties", [])]
        assert "title" in props, (
            f"Expected 'title' in properties, got: {props}"
        )

    def test_private_method_excluded(self):
        """Private method '_internal' must NOT appear in extracted methods."""
        classes = _run_extraction()
        methods = [m["name"] for m in classes["SimpleDocument"].get("methods", [])]
        assert "_internal" not in methods, (
            f"Private method '_internal' must be excluded, but found in: {methods}"
        )
