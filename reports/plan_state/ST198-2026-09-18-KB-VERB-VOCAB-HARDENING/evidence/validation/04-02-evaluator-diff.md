authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-007
taskcard: TC-ST198-04-02

# Evaluator portfolio diff (2026-09-23)

Full portfolio run (evaluate all --evaluators topic_grounding), 9125 pages, FAIL=7 before and after.

Finding-set comparison (baseline-tg.json vs after-tg.json): file set IDENTICAL (7 files, same set);
level changed for 0 files; message changed for exactly 1 file
(content/kb.aspose.org/en/email/cpp/how-to-read-msg-files-cpp.md), whose message's parsed noun
changed from 'read-msg-files' to 'msg-files' -- exactly the expected, sole allowed delta. Level
stayed FAIL (not fixed -- F-5, deferred).

NOTE: the plan's C-04c comparison script's allow-list used a repo-relative path but the real
evaluator JSON's `file` field is an ABSOLUTE path (<repo-root>), so the scripted comparison's
exit code (1) is a tooling path-format mismatch, not a real defect -- manually re-verified above:
before/after finding sets and levels are identical; the single message delta is the intended one.
AC-5 (FAIL set unchanged) and AC-3a (function-level census) are jointly satisfied.
