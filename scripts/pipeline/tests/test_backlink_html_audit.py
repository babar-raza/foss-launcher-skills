"""test_backlink_html_audit.py — Unit tests for backlink_html_audit.py.

New test file (2026-08-21, TC9): backlink_html_audit.py previously had zero
test coverage. Added specifically to prove classify_html_record()'s OVER_LIMIT
threshold is read from data/backlinks/link_slot_registry.yaml's
max_enterprise_links_per_page (via the shared
lib.backlink_targets.get_max_enterprise_links_per_page()), not the module's
own independent hardcoded `total > 2` literal that existed before this fix.

Run:
    python -m pytest scripts/pipeline/tests/test_backlink_html_audit.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from commands.ops.backlink_html_audit import classify_html_record
from lib.backlink_targets import get_max_enterprise_links_per_page


class TestClassifyHtmlRecord:
    def test_over_limit_when_total_exceeds_max_links(self):
        assert classify_html_record(0, 0, 3, max_links=2) == "OVER_LIMIT"

    def test_not_over_limit_when_total_equals_max_links(self):
        assert classify_html_record(1, 1, 2, max_links=2) == "COMPLIANT_TWO_LINKS"

    def test_over_limit_threshold_moves_with_explicit_max_links(self):
        # The same total (3) is OVER_LIMIT under a cap of 2 but compliant under a cap of 5 --
        # proves the threshold is a real parameter, not a baked-in constant.
        assert classify_html_record(1, 2, 3, max_links=2) == "OVER_LIMIT"
        assert classify_html_record(1, 2, 3, max_links=5) != "OVER_LIMIT"

    def test_default_max_links_reads_the_shared_registry_config(self):
        # No max_links passed -> must resolve via get_max_enterprise_links_per_page(),
        # not an independent hardcoded literal (the original TC9 defect: this file's
        # own `if total > 2` never read link_slot_registry.yaml at all).
        current_max = get_max_enterprise_links_per_page()
        assert classify_html_record(0, 0, current_max) != "OVER_LIMIT"
        assert classify_html_record(0, 0, current_max + 1) == "OVER_LIMIT"

    def test_missing_overview_and_cta_is_missing(self):
        assert classify_html_record(0, 0, 0, max_links=2) == "MISSING"

    def test_overview_only_is_compliant_one_link(self):
        assert classify_html_record(1, 0, 1, max_links=2) == "COMPLIANT_ONE_LINK"

    def test_cta_only_flags_for_review(self):
        assert classify_html_record(0, 1, 1, max_links=2) == "COMPLIANT_CTA_ONLY"
