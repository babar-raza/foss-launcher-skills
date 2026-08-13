"""MT030-2026-08-13: backlog_parser.py -- shared BACKLOG.md table parser."""
# sys.path is set by tests/conftest.py
from backlog_parser import parse_table_rows, parse_backlog_file, extract_product_key


SAMPLE_BACKLOG = """# Backlog

## Active (P0–P1)

| ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated |
|----|-----|--------|-------|--------|----------|------|------|-------|------|---------|---------|
| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java new upstream drift found... | queued | P1 | L | 0 | 0 | — | — | 2026-08-01 |
| 3D-NET-REFRESH-002 | knowledge | HIGH | 3d/net refresh -- new upstream drift | REMEDIATION_REQUIRED | P1 | M | 0 | 9 | typed-zooming-meteor | truth-audit-fail | 2026-08-01 |
| SOME-OPS-ROW-001 | ops | LOW | Not a knowledge-drift row | CLOSED | P4 | XS | 0 | 1 | plan-name | — | 2026-06-10 |

## Queued

| ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated |
|----|-----|--------|-------|--------|----------|------|------|-------|------|---------|---------|
| G-16 | ops | LOW | attach_evidence.py duplicated-frontmatter bug | queued | P2 | S | 0 | 0 | — | — | 2026-07-16 |

## Recently Completed

| ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated |
|----|-----|--------|-------|--------|----------|------|------|-------|------|---------|---------|
| OLD-ROW-001 | ops | LOW | Should not appear -- outside Active/Queued | CLOSED | P4 | XS | 0 | 1 | plan | — | 2026-01-01 |
"""


class TestParseTableRows:
    def test_extracts_active_rows(self):
        rows = parse_table_rows(SAMPLE_BACKLOG)
        ids = {r["id"] for r in rows}
        assert "PDF-JAVA-REFRESH-003" in ids
        assert "3D-NET-REFRESH-002" in ids
        assert "SOME-OPS-ROW-001" in ids

    def test_extracts_queued_rows(self):
        rows = parse_table_rows(SAMPLE_BACKLOG)
        ids = {r["id"] for r in rows}
        assert "G-16" in ids

    def test_excludes_recently_completed_rows(self):
        """Only Active and Queued sections are in scope -- Recently Completed
        is historical archive, not live reconciliation-eligible state."""
        rows = parse_table_rows(SAMPLE_BACKLOG)
        ids = {r["id"] for r in rows}
        assert "OLD-ROW-001" not in ids

    def test_cat_column_extracted(self):
        rows = parse_table_rows(SAMPLE_BACKLOG)
        row = next(r for r in rows if r["id"] == "PDF-JAVA-REFRESH-003")
        assert row["cat"] == "knowledge"

    def test_updated_column_extracted(self):
        rows = parse_table_rows(SAMPLE_BACKLOG)
        row = next(r for r in rows if r["id"] == "PDF-JAVA-REFRESH-003")
        assert row["updated"] == "2026-08-01"

    def test_status_and_title_preserved(self):
        rows = parse_table_rows(SAMPLE_BACKLOG)
        row = next(r for r in rows if r["id"] == "3D-NET-REFRESH-002")
        assert row["status"] == "REMEDIATION_REQUIRED"
        assert row["title"].startswith("3d/net refresh")


class TestParseBacklogFile:
    def test_missing_file_returns_empty_list(self, tmp_path):
        assert parse_backlog_file(tmp_path / "nonexistent.md") == []

    def test_reads_real_file(self, tmp_path):
        p = tmp_path / "BACKLOG.md"
        p.write_text(SAMPLE_BACKLOG, encoding="utf-8")
        rows = parse_backlog_file(p)
        assert len(rows) == 4  # 3 Active + 1 Queued


class TestExtractProductKey:
    def test_extracts_family_platform(self):
        assert extract_product_key("pdf/java new upstream drift found by...") == "pdf/java"

    def test_extracts_from_3d_net(self):
        assert extract_product_key("3d/net refresh -- new upstream drift") == "3d/net"

    def test_returns_none_for_no_slash(self):
        assert extract_product_key("Not a knowledge-drift row") is None

    def test_returns_none_for_empty_title(self):
        assert extract_product_key("") is None

    def test_returns_none_for_url_like_prefix(self):
        assert extract_product_key("https://example.com/foo needs fixing") is None

    def test_returns_none_for_malformed_slash_token(self):
        assert extract_product_key("G-16/attach_evidence.py bug found") is None
