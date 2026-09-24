"""TC-TSGAP-07 (2026-09-24, Seventh Pass of the pdf/typescript hardening
plan): _compute_reachable's own documented "unknown collapses to True"
contract (never fabricate a False) means every TS/JS entry's
reachable=True is inherently ambiguous -- it cannot be told apart from
"confirmed reachable via a real resolved barrel" without an explicit
signal. Found live on cells/typescript: package.json's `main` resolves to
a real, existing, but non-exporting demo index.ts, so export_surface()
correctly returns (None, None) per its own fail-safe contract, and every
one of 131 entries silently defaulted to reachable=True with zero actual
verification -- a real fidelity gap, though not a currently-active
content-correctness bug (reference_filter.py's REACHABILITY_ENFORCED_PLATFORMS
gate only ever REMOVES a page on a confirmed reachable=False, so it can
never wrongly suppress a page off this collapsed default).

scout_report.json now carries a `ts_reachability_signal` field
("confirmed" | "unknown_no_entry_resolved" |
"unknown_entry_resolved_but_unenumerable") alongside the existing
`ts_entry_point` field, making the distinction operator-visible without
changing any per-entry reachable value or the fail-safe contract itself.
"""
# sys.path is set by tests/conftest.py -- no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestTsReachabilitySignal:
    def test_confirmed_when_barrel_resolves_and_exports_something(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "index.ts", "export class Widget {}\n")
        _write(tmp_path / "package.json", '{"main": "src/index.ts"}\n')
        parser = scout.get_parser("typescript")
        *_, scout_report = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        assert scout_report["ts_reachability_signal"] == "confirmed"
        assert scout_report["ts_entry_point"] == "src/index.ts"

    def test_unknown_no_entry_resolved_when_nothing_exists_on_disk(self, tmp_path):
        pkg_root = tmp_path / "src"
        _write(pkg_root / "widget.ts", "export class Widget {}\n")
        # No package.json, no index.ts anywhere -- resolve_entry_point()
        # itself returns None.
        parser = scout.get_parser("typescript")
        *_, scout_report = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        assert scout_report["ts_reachability_signal"] == "unknown_no_entry_resolved"
        assert scout_report["ts_entry_point"] == ""

    def test_unknown_entry_resolved_but_unenumerable_reproduces_cells_typescript_shape(self, tmp_path):
        """The exact real-world shape this card was filed against: a real,
        on-disk, package.json-declared entry point that exists but exports
        nothing at all (a demo/test-harness script)."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "widget.ts", "export class Widget {}\n")
        _write(tmp_path / "index.ts", "console.log('just a demo script, no exports');\n")
        _write(tmp_path / "package.json", '{"main": "index.ts"}\n')
        parser = scout.get_parser("typescript")
        *_, scout_report = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
        assert scout_report["ts_reachability_signal"] == "unknown_entry_resolved_but_unenumerable"
        assert scout_report["ts_entry_point"] == "index.ts"

    def test_signal_key_absent_for_non_ts_platforms(self, tmp_path):
        """Regression guard matching this file's own existing convention
        (see the ts_entry_point comment in api_surface.py): the new key must
        never appear for python/rust/etc, only for typescript/javascript --
        an unconditional key broke extraction_goldens.py's byte-for-byte
        report parity check the last time this shape of field was added."""
        pkg_root = tmp_path / "src"
        _write(pkg_root / "widget.py", "class Widget:\n    pass\n")
        parser = scout.get_parser("python")
        *_, scout_report = extract_api_surface(parser, "python", pkg_root, tmp_path, "fake")
        assert "ts_reachability_signal" not in scout_report
        assert "ts_entry_point" not in scout_report
