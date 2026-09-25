authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-004, REQ-KBV-007, REQ-KBV-009
taskcard: TC-ST198-04-05

# Rerun stability and scope purity (2026-09-23)

- Appendix A probe re-run with PYTHONHASHSEED=1 and =2 (both PYTHONIOENCODING=utf-8): sha256
  d08bc23879336f3b260e80ab97f49fa385391150c22cda07c0271404077e1e4d for seed 1, seed 2, and the
  seed-0 after-probe.txt captured in 04-01 -- all three byte-identical.
- C-02 (9 files) run twice: 254 passed both times, identical counts.
- git apply -R --check on the current-tip cumulative patches for site_planner.py,
  topic_grounding.py and content_eval/__init__.py: exit 0 for all three (proves each patch
  contains only our own hunks and applies cleanly against the exact current tree state).
- git status --porcelain on the 5 allowed files: exactly the 5, all "M", nothing else.
- git status --porcelain on test_site_planner_kb.py and test_check_kb_slug_quality.py: empty.
- git status --porcelain on content/kb.aspose.org/ and knowledge/: 0 lines (no content/knowledge
  file touched).
