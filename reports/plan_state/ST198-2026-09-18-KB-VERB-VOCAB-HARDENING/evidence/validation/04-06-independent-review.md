authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-001, REQ-KBV-002, REQ-KBV-004, REQ-KBV-006
taskcard: TC-ST198-04-06

# Independent review (2026-09-23)

Reviewer: fresh-context general-purpose subagent (agentId a6da8827d78054c7a), given only the
cumulative diff + background description + 9 explicit verification questions (§5.1, AC list,
§3.1). It independently re-ran the affected test suites live rather than trusting the diff.

VERDICT: ACCEPT (no blocking issues).

All 9 explicit checks confirmed by the reviewer via independent source reading + live test runs
(30 + 26 + 139 = 195 tests re-run by the reviewer itself):
1. Forward-path (detect_kb_verb) row order and results unchanged -- confirmed.
2. _KB_REVERSE_VERB_VOCAB never includes a hint-only raw keyword (msg/mesh/cfb/comment/etc) --
   confirmed (every hint row's canonical verb is already a synonym-row canonical).
3. if-verb guard is a pure gate, non-empty-verb behavior byte-identical to before -- confirmed.
4. Only the empty-verb false-positive case changes for derived slugs -- confirmed, no broader
   behavior change.
5. topic_grounding.py's ImportError fallback stub matches the OLD degraded behavior exactly --
   confirmed by reading both versions.
6. No vacuous test found. One test's inline comment was mislabeled (nit, see findings).
7. No out-of-scope file touched; no dead KB_PLATFORM_SUFFIX import left in topic_grounding.py.
8. Sort key (-len, alpha) is a deterministic strict total order -- no risk.
9. CRLF warnings are pre-existing working-tree normalization noise, not diff content.

Findings (non-blocking, triaged):
- [non-blocking, FIXED THIS SESSION] topic_grounding.py's comment undersold that a THIRD,
  independently-maintained verb vocabulary exists in
  scripts/ci/checks/check_kb_slug_quality.py (pre-existing drift, F-2, out of scope for this
  fix). Comment corrected in place (see 04-06-review-packet-pre-comment-fix.diff for the
  pre-fix diff vs the current one); re-ran test_topic_grounding.py after the comment edit:
  26 passed, unchanged.
- [nit, not changed] test_synonym_led_discovered_slug_logs_no_duplication_warning is grouped
  under the "Check 2 empty-verb guard" heading but its example slug ('how-to-read-msg-files-cpp')
  actually parses a non-empty verb ('read'), so it exercises the reverse-vocabulary synonym fix
  more than the if-verb guard specifically. Test is correct, only its section placement is
  imprecise; not worth a further source edit.
- [nit] CRLF conversion warnings: cosmetic, no action.

Disposition: ACCEPT, one cheap non-blocking finding fixed, two nits recorded and left as-is.
No REWORK_REQUIRED.
