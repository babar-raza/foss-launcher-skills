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
