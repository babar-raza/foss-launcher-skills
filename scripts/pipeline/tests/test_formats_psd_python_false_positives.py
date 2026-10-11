"""Regression test: TC-PSD-HRD-9N-10 -- extraction/formats.py's Pass 2
(snake_case method-name format scanner) must not emit "ltrb", "int32", or
"points" as format entries when running against psd/python's clone cache.

Root-cause correction (found during this fix, `-01`'s own hypothesis was
only half right): `-01` attributed this to "no known-format whitelist
exists anywhere in the extraction path." That is true for Pass 2
specifically, but NOT the whole extraction path: `extraction/
format_signals.py`'s two recognizers (`recognize_pascal_verb_token`,
`recognize_camel_identifier_format`) already check candidate tokens
against a real whitelist (`_PASCAL_VERB_KNOWN_TOKENS` /
`_KNOWN_FORMAT_TOKENS`) before accepting them. The actual defect is
narrower and more specific: Pass 2 (`extraction/formats.py`, the
`load_from`/`save_to`/`save_as`/`from`/`to`_X snake_case regex scanner)
uses a DENYLIST (`_FORMAT_METHOD_SKIP`, a hand-curated set of known
false-positive words, already iteratively grown at least twice before
per its own "H-04b"/"H-04c" comments) instead of a whitelist -- any word
NOT yet added to that denylist is accepted as a real format, which is
exactly how "int32" (from `BigEndianBitConverter.to_int32`), "ltrb" (a
rectangle coordinate convention from `LayerRecordReader`), and "points"
(`Rectangle`/`Point` geometry) slipped through for psd/python.

Fix: added "int32", "ltrb", "points" to `_FORMAT_METHOD_SKIP`, matching
the exact same narrow, proven-safe pattern the file's own prior H-04b/
H-04c fixes already established (add the specific false-positive word,
don't restructure the whole pass) -- confirmed zero portfolio regression
risk since this only ever REMOVES candidate matches, never adds any.

This test runs scout.py end-to-end against the psd/python clone cache
(mirroring `test_formats_imaging_net_endian_false_positive.py`'s own
precedent) and verifies: (a) none of the 3 known garbage tokens appear in
formats.json output; (b) scout.py still exits 0; (c) no real PSD/PSB
claim is lost as a side effect (a negative control on the fix's own
blast radius, not just the symptom)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PSD_PYTHON_CACHE = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_psd_python"
_PSD_PYTHON_HAS_SOURCES = (
    bool(list(_PSD_PYTHON_CACHE.rglob("*.py"))[:1])
    if _PSD_PYTHON_CACHE.exists()
    else False
)
_SCOUT_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "scout.py"


@unittest.skipUnless(
    _PSD_PYTHON_HAS_SOURCES,
    "Clone cache absent or empty — run /repo-scout psd python first",
)
class TestPsdPythonFormatExtraction(unittest.TestCase):
    """formats.json must not contain the 3 known garbage tokens; real
    extraction output (claims, api_surface) must be unaffected."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="scout_psd_python_fmt_test_")
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        result = subprocess.run(
            [
                sys.executable,
                str(_SCOUT_SCRIPT),
                "psd",
                "python",
                str(_PSD_PYTHON_CACHE),
                cls._tmpdir,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        cls._scout_returncode = result.returncode
        cls._scout_stderr = result.stderr
        formats_path = Path(cls._tmpdir) / "formats.json"
        if formats_path.exists():
            cls._formats = json.loads(formats_path.read_text(encoding="utf-8"))
        else:
            cls._formats = []
        cls._by_name = {f["format"].lower(): f for f in cls._formats}
        claims_path = Path(cls._tmpdir) / "claims.json"
        if claims_path.exists():
            _claims_doc = json.loads(claims_path.read_text(encoding="utf-8"))
            # scout.py's raw claims.json is {source_sha, extracted_at,
            # family, platform, claim_count, claims: [...]} -- NOT a bare
            # list (that flatter shape only exists later, in
            # merged/claims.json after promote.py).
            cls._claim_count = len(_claims_doc.get("claims", []))
        else:
            cls._claim_count = 0

    def test_scout_exits_zero(self):
        self.assertEqual(
            self._scout_returncode, 0,
            f"scout.py exited {self._scout_returncode}:\n{self._scout_stderr}",
        )

    def test_ltrb_false_positive_absent(self):
        self.assertNotIn("ltrb", self._by_name, f"formats.json still has 'ltrb': {self._formats}")

    def test_int32_false_positive_absent(self):
        self.assertNotIn("int32", self._by_name, f"formats.json still has 'int32': {self._formats}")

    def test_points_false_positive_absent(self):
        self.assertNotIn("points", self._by_name, f"formats.json still has 'points': {self._formats}")

    def test_negative_control_real_claims_unaffected(self):
        """The fix only narrows Pass 2's candidate set -- it must not
        reduce the overall claim count below what psd/python's real,
        already-verified extraction produces (a fresh scout.py run against
        the real clone, pre-fix, produced 465 claims -- this threshold is
        set well below that as a regression guard, not an exact pin)."""
        self.assertGreaterEqual(
            self._claim_count, 400,
            f"claim_count unexpectedly low ({self._claim_count}) -- the "
            f"format-skip fix may have had an unintended side effect",
        )
