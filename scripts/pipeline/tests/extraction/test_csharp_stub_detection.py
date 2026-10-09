"""Regression tests for TC-PSD-HRD-9N-4 — C# stub-throw detection for
`merged/limitations.md` generation misses `NotSupportedException`.

Found live during MT076 (psd/net launch, KNW-NET-01-04 truth cross-check):
`knowledge/psd/net/merged/limitations.md` reported "No NotImplementedError
patterns detected" despite 8 genuine, deliberate `NotSupportedException`
stub throws in the real source (`Layer.cs` x3, `PsdImage.cs` x4,
`Resources/PreservedResourceBlock.cs` x1) — all expression-bodied property
setters, e.g.::

    set => throw new NotSupportedException("Changing layer channel information is not supported by this FOSS build.");

**Root-cause correction (found during this fix, -01's own hypothesis was
wrong about WHICH mechanism produces limitations.md):** `-01`'s
investigate note attributed this to `api_surface.py::_is_csharp_stub()`
(a block-vs-arrow-expression body-shape gap feeding a `stub` flag used
only by `batch_reference.py`/`regenerate_reference.py` for reference-page
generation — a real, separate, independently-confirmed defect, but NOT
the mechanism that builds `limitations.md` at all). `limitations.md` is
actually built by `extraction/scout.py::Scout._detect_limitations()`,
which scans raw source text line-by-line against
`extraction/tree_helpers.py::_NOT_IMPL_PATTERNS[language]` — and that
regex for `"csharp"` matches ONLY `NotImplementedException`, never
`NotSupportedException` (the exception the real source actually throws).
Confirmed by reading `knowledge/psd/net/merged/limitations.md` directly
(still says "No NotImplementedError patterns detected" before this fix).

The `api_surface.py::_is_csharp_stub()` gap is real and tracked
separately (same taskcard's remaining scope, deferred this tick due to a
concurrent-session skill-context conflict on that file — see this
taskcard's own `-02` evidence) — these tests cover only the
`_NOT_IMPL_PATTERNS["csharp"]` regex gap that actually produces the
measured `limitations.md` symptom.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from extraction.tree_helpers import _NOT_IMPL_PATTERNS  # noqa: E402

_CSHARP_PATTERN = _NOT_IMPL_PATTERNS["csharp"]


class TestCSharpNotImplPatternMatchesAllStubExceptionNames:
    def test_matches_not_supported_exception(self):
        """The exact real-world line this bug was found on (psd/net
        Layer.cs:208) -- the measured defect this fix exists to close."""
        line = (
            '        set => throw new NotSupportedException('
            '"Changing layer channel information is not supported by this FOSS build.");'
        )
        assert _CSHARP_PATTERN.search(line), (
            "the csharp not-implemented pattern must match "
            "NotSupportedException -- this is the exact live regression "
            "found on psd/net's Layer.cs/PsdImage.cs/PreservedResourceBlock.cs "
            "(8 real stubs, all silently missing from limitations.md)"
        )

    def test_matches_not_supported_exception_block_bodied(self):
        """Same exception type, but in the older block-bodied form (`{ throw ...; }`)
        -- confirms the fix is about the EXCEPTION NAME, not body shape."""
        line = '        set { throw new NotSupportedException("nope"); }'
        assert _CSHARP_PATTERN.search(line)

    def test_matches_unsupported_operation_exception(self):
        """A second real exception name api_surface.py's own _STUB_EXCEPTION_RE
        already recognizes for the SAME semantic concept elsewhere in this
        codebase -- the csharp limitations pattern should be consistent
        with it, not narrower."""
        line = '        set => throw new NotSupportedOperationException("nope");'
        assert _CSHARP_PATTERN.search(line)

    def test_negative_control_still_matches_original_not_implemented_exception(self):
        """The fix must not narrow or break the ORIGINAL, already-working
        case -- NotImplementedException detection predates this fix and
        must keep working."""
        line = '        public void Foo() { throw new NotImplementedException(); }'
        assert _CSHARP_PATTERN.search(line)

    def test_negative_control_does_not_match_unrelated_throw(self):
        """A throw of an unrelated exception type must NOT be misclassified
        as a stub/limitation."""
        line = '        set => throw new ArgumentNullException(nameof(value));'
        assert not _CSHARP_PATTERN.search(line)


# ---------------------------------------------------------------------------
# TC-PSD-HRD-9N-27 — api_surface.py::_is_csharp_stub() and property-setter
# stub detection (a SEPARATE defect from HRD-9N-4 above: that fix closed the
# limitations.md regex gap; this one closes a different gap in a different
# function, feeding a different consumer -- batch_reference.py's/
# regenerate_reference.py's reference-page `stub` rendering).
#
# Confirmed via a direct tree-sitter parse probe (not guessed): C#'s
# `set => throw new X(...);` parses as
# accessor_declaration > arrow_expression_clause > throw_expression -- a
# DIFFERENT node shape than the block-bodied `{ throw ...; }` form
# (which produces a `block` > `throw_statement`). The original
# `_is_csharp_stub()` only ever checked for `block`, so it returned False
# immediately for every real, expression-bodied stub in this portfolio
# (psd/net's Layer.cs/PsdImage.cs/PreservedResourceBlock.cs use the arrow
# form exclusively, zero block-bodied occurrences). Separately, the
# property_declaration extraction branch never called ANY stub-detection
# function for either accessor at all.
# ---------------------------------------------------------------------------

import tree_sitter_language_pack as _tsl  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from extraction.api_surface import _is_csharp_stub, extract_api_surface  # noqa: E402
from extraction.tree_helpers import find_child_by_type  # noqa: E402

_CS_PARSER = _tsl.get_parser("csharp")


def _parse_csharp_first_method(src: str):
    """Parse a minimal C# source snippet and return the first
    method_declaration node found (depth-first)."""
    tree = _CS_PARSER.parse(src.encode("utf-8"))

    def _walk(node):
        if node.type == "method_declaration":
            return node
        for ch in node.children:
            found = _walk(ch)
            if found is not None:
                return found
        return None

    return _walk(tree.root_node)


def _parse_csharp_first_setter(src: str):
    """Parse a minimal C# source snippet and return the first property's
    `set`/`init` accessor_declaration node."""
    tree = _CS_PARSER.parse(src.encode("utf-8"))

    def _walk(node):
        if node.type == "property_declaration":
            acc_list = find_child_by_type(node, "accessor_list")
            if acc_list is not None:
                for acc in acc_list.children:
                    if acc.type == "accessor_declaration":
                        text = _tsl_node_text(acc, src)
                        if text.lstrip().startswith(("set", "init")):
                            return acc
        for ch in node.children:
            found = _walk(ch)
            if found is not None:
                return found
        return None

    return _walk(tree.root_node)


def _tsl_node_text(node, src: str) -> str:
    return src.encode("utf-8")[node.start_byte:node.end_byte].decode("utf-8")


class TestIsCSharpStubExpressionBodied:
    def test_expression_bodied_method_stub_detected(self):
        """A bare, expression-bodied METHOD stub (not just a property
        setter) must also be recognized -- the fix is general, not
        property-specific, even though no real portfolio example of this
        exact shape was found during this investigation (psd/net's own
        stubs are all property setters)."""
        src = (
            "class Foo {\n"
            "    public void Bar() => throw new NotSupportedException(\"nope\");\n"
            "}\n"
        )
        node = _parse_csharp_first_method(src)
        assert node is not None
        assert _is_csharp_stub(node) is True

    def test_block_bodied_method_stub_still_detected(self):
        """Negative control: the ORIGINAL, already-working block-bodied
        case must keep working."""
        src = (
            "class Foo {\n"
            "    public void Bar() { throw new NotSupportedException(\"nope\"); }\n"
            "}\n"
        )
        node = _parse_csharp_first_method(src)
        assert node is not None
        assert _is_csharp_stub(node) is True

    def test_expression_bodied_non_stub_method_not_flagged(self):
        """Negative control: a real, working expression-bodied method
        (no throw at all) must not be misclassified as a stub."""
        src = (
            "class Foo {\n"
            "    public int Bar() => 42;\n"
            "}\n"
        )
        node = _parse_csharp_first_method(src)
        assert node is not None
        assert _is_csharp_stub(node) is False


class TestPropertySetterStubDetection:
    def test_real_psd_net_setter_shape_flagged_as_setter_stub(self):
        """The exact real-world shape found live on psd/net's Layer.cs:208
        -- a property with a working getter and a setter that
        unconditionally throws."""
        src = (
            "class Layer {\n"
            "    public ChannelInformation[] ChannelInformation {\n"
            "        get => _channelInfo;\n"
            "        set => throw new NotSupportedException(\"Changing layer channel information is not supported by this FOSS build.\");\n"
            "    }\n"
            "}\n"
        )
        acc = _parse_csharp_first_setter(src)
        assert acc is not None
        assert _is_csharp_stub(acc) is True, (
            "the setter's own body must be recognized as a stub throw -- "
            "this is the exact live shape found on psd/net's "
            "Layer.ChannelInformation (and 7 other real properties across "
            "Layer.cs/PsdImage.cs/PreservedResourceBlock.cs)"
        )

    def test_negative_control_working_setter_not_flagged(self):
        """A real, working setter (no throw) must not be misclassified."""
        src = (
            "class Layer {\n"
            "    public string Name {\n"
            "        get => _name;\n"
            "        set => _name = value;\n"
            "    }\n"
            "}\n"
        )
        acc = _parse_csharp_first_setter(src)
        assert acc is not None
        assert _is_csharp_stub(acc) is False

    def test_extract_api_surface_sets_setter_stub_field(self):
        """End-to-end: extract_api_surface() (the real public entry point
        api_surface.py exposes, not just the internal helper) must set
        `setter_stub: True` on the property entry for the real psd/net
        shape, and must NOT set it for a normal working property."""
        src = (
            "namespace Foo {\n"
            "public class Layer {\n"
            "    public ChannelInformation[] ChannelInformation {\n"
            "        get => _channelInfo;\n"
            "        set => throw new NotSupportedException(\"nope\");\n"
            "    }\n"
            "    public string Name {\n"
            "        get => _name;\n"
            "        set => _name = value;\n"
            "    }\n"
            "}\n"
            "}\n"
        )
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            src_path = tmp_path / "Layer.cs"
            src_path.write_text(src, encoding="utf-8")
            classes, _claims, _scanned, _pkgs, _report = extract_api_surface(
                _CS_PARSER, "csharp", tmp_path, tmp_path, "psd",
            )
        layer = next(c for c in classes if c["name"] == "Layer")
        props_by_name = {p["name"]: p for p in layer["properties"]}
        assert props_by_name["ChannelInformation"].get("setter_stub") is True
        assert "setter_stub" not in props_by_name["Name"] or not props_by_name["Name"]["setter_stub"]
