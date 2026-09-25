branch: main
HEAD: ac3672f7b8a94c10f727b71e68ca195783a7717c
authored anchor: c47e56659a081352cf84264be60ee7bc50127bd7
commits since anchor: 81
-- commits touching our 6 files since anchor --
-- dirty status of our 6 files --
(empty=clean)
-- dirty total --
136
-- live skill contexts --
== reports/skill-context/active/29feae0b-540b-4878-bfee-c84500323e4a.json ==
{
  "skill_id": "S-115",
  "context_type": "skill",
  "scope_patterns": [
    "scripts/pre-commit-audit.sh",
    "scripts/pipeline/tests/test_precommit_audit_step_numbering.py",
    "scripts/pipeline/tests/test_precommit_full_run.py",
    "scripts/ci/**",
    ".github/workflows/**",
    "docs/operations/**",
    "scripts/pipeline/config/workflow_*",
    "scripts/pipeline/lib/workflow_*",
    "scripts/pipeline/commands/ops/workflow_*",
    "scripts/pipeline/tests/test_workflow_*",
    "scripts/pipeline/config/registry.yaml"
  ],
  "started_at": "2026-09-19T12:20:13.142332Z",
  "session_id": "29feae0b-540b-4878-bfee-c84500323e4a",
  "last_touched_at": "2026-09-19T12:50:46.242771Z"
}

-- anchor greps --
129:_VERB_KEYWORDS: list[tuple[list[str], str]] = [
1771:    _known_verbs: list[str] = sorted(
1791:        for kv in _known_verbs:
82:_KNOWN_VERBS: list[str] = sorted(
154:    for kv in _KNOWN_VERBS:
93:    "topic_grounding": "1",  # CE-02 (2026-09-17 healing plan G-03): initial version
-- import check --
True True True
