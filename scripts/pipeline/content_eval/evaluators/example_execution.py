"""Example execution evaluator (C8, category EX).

MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION.

EXPERIMENTAL + DEFAULT (the code_block_api precedent): runs at Stage 7 on
every page and appears in the manifest/report, but is deliberately absent
from config.CANONICAL_EVALUATORS, so its findings never affect the
frontmatter grade letter (models.py's grade computation filters findings to
CANONICAL_EVALUATORS only -- confirmed by reading models.py:304/414 before
writing this module).

Two independent, inherit-first signals per fenced code block:

1. ``lookup_proof`` -- an exact ``sha256_norm`` match against this
   product's ``snippets_index.json`` (the same C6 "verify at the source"
   index ``audit/snippets.py:verify_snippet_coverage`` already reads, via
   the identical map-then-lookup shape). If the matching entry carries a
   populated ``execution_proof``, report what it proves (INFO "inherited")
   or, if its ``clone_head``/``runner_version`` no longer match this
   product's current state, how it has gone stale (WARN "stale_by"). No
   matching entry -- or a match whose own ``execution_proof`` is still
   unpopulated -- WARNs "novel-unverified": absence of proof is never
   silently treated as a pass. As of C10's own live measurement, zero of
   this portfolio's ~32 real snippet indexes have ``execution_proof``
   populated yet (the post-promote sweep C6 deferred), so today every real
   page falls straight to one page-level "index has no code_sha256 yet"
   INFO (mirroring ``audit/snippets.py``'s own SKIP convention) rather than
   a WARN per block -- this activates automatically, no code change needed,
   once a product is swept.
2. A live tier-1 syntax check via the centralized
   ``lib.example_verification.syntax.check_syntax`` -- this evaluator never
   acquires (``allow_acquire`` stays False), so it can never itself produce
   proof above tier 1; only *inherited* proof from the snippet index can
   carry tier 2/3 (hence "inherit-first" in the taskcard's own title). FAILs
   only when a real parse ran and found a genuine error (``SYNTAX-ERROR``);
   a missing grammar (``GRAMMAR-UNAVAILABLE``, proof_tier=0) is a WARN, never
   a FAIL and never a silent pass, since no check actually ran.

Budget: a wall-clock ceiling per page (default 60s, matching the governing
plan's cost model, ``configure(budget=...)``) -- blocks beyond it get one
WARN ``BUDGET-EXHAUSTED`` rather than being silently skipped or blocking
the whole evaluation run.

Category: EX (Example Execution)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# sibling-import guard: sub-packages must add the pipeline root (for
# `lib.example_verification.*`) and pipeline/lib (for bare `knowledge_core`)
# so they can import both shapes regardless of import order -- the same
# guard `audit/snippets.py` and `code_block_api.py` already use.
_HERE = Path(__file__).resolve().parent.parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from knowledge_core import Knowledge  # noqa: E402
from lib.example_verification import RUNNERS_MODULE_VERSION  # noqa: E402
from lib.example_verification.code_fences import enumerate_code_blocks  # noqa: E402
from lib.example_verification.registry import NON_EXECUTABLE_LANGS  # noqa: E402
from lib.example_verification.syntax import check_syntax  # noqa: E402

# Independent-review finding (round 1): registry.NON_EXECUTABLE_LANGS is a
# "never executable in any language" set and does not include shell-family
# tags -- unlike the sibling code_syntax_check.py evaluator's own
# `_SKIP_LANGS`, which already excludes bash/shell/sh. syntax.py's
# tree-sitter loader has no grammar entry for any shell-family language at
# all (see its `_CANONICAL_TAGS`), so every shell/install-command block in
# the entire portfolio would otherwise get a permanent, predictable
# GRAMMAR-UNAVAILABLE WARN forever -- not a real signal, just noise.
# registry.py is out of this taskcard's allowed_paths, so this supplements
# NON_EXECUTABLE_LANGS locally rather than editing the shared set.
_SHELL_LANGS = frozenset({"bash", "sh", "shell", "powershell", "bat", "cmd"})

# --- Test seam (configure() pattern; see module_compilability.py precedent) ---
_MAX_TIER = 2
_ALLOW_ACQUIRE = False
_BUDGET_SECONDS = 60.0


def configure(*, max_tier: int = 2, allow_acquire: bool = False, budget: float = 60.0) -> None:
    """Test seam: override the inherited-proof tier ceiling, the (always-off
    today) acquire policy, and the per-page wall-clock budget. Call with no
    args to restore defaults."""
    global _MAX_TIER, _ALLOW_ACQUIRE, _BUDGET_SECONDS
    _MAX_TIER = max_tier
    _ALLOW_ACQUIRE = allow_acquire
    _BUDGET_SECONDS = budget


def _norm_hash_index(knowledge: Any) -> dict[str, dict]:
    """Same map shape as audit/snippets.py:verify_snippet_coverage -- kept
    independent (not imported) since that function returns Findings against
    a different Finding type (token_ops.Finding, not content_eval's)."""
    index: dict[str, dict] = {}
    for entry in getattr(knowledge, "snippet_index", None) or []:
        if not isinstance(entry, dict):
            continue
        code_sha = entry.get("code_sha256")
        if isinstance(code_sha, dict) and code_sha.get("norm"):
            index[code_sha["norm"]] = entry
    return index


def _stale_component(proof: dict, family: str, platform: str) -> "str | None":
    """Return the first component that no longer matches this product's
    current state, or None if the inherited proof still looks fresh. Never
    fabricates staleness when the current value can't be determined (a
    missing clone cache is not evidence the proof is stale)."""
    try:
        from core.clone_cache import clone_head_sha
        current_head = clone_head_sha(family, platform)
    except Exception:
        current_head = None
    if current_head and proof.get("clone_head") and proof["clone_head"] != current_head:
        return "clone_head"
    if proof.get("runner_version") and proof["runner_version"] != RUNNERS_MODULE_VERSION:
        return "runners_version"
    return None


def _lookup_proof(entry: "dict | None", family: str, platform: str):
    """Returns (status, detail) where status is one of "inherited",
    "stale_by", "novel-unverified". detail is the matching index entry (or
    None). `max_tier` (module `configure()`) never downgrades inherited
    proof -- a higher inherited tier is strictly more trustworthy, never
    less; it only ever ceilings this evaluator's own LIVE checks, which
    today never exceed tier 1 regardless (this evaluator never acquires)."""
    if entry is None:
        return "novel-unverified", None
    proof = entry.get("execution_proof")
    if not isinstance(proof, dict) or not proof.get("tier"):
        return "novel-unverified", entry
    stale = _stale_component(proof, family, platform)
    if stale:
        return "stale_by", entry
    return "inherited", entry


class ExampleExecutionEvaluator(BaseEvaluator):
    """Inherit-first example-execution advisory: reports whether each code
    block has real execution proof on record (from the C6 snippet index)
    and runs one live tier-1 syntax check via the centralized loader.
    EXPERIMENTAL — never affects the canonical grade.
    """

    name = "example_execution"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not isinstance(knowledge, Knowledge):
            return []

        findings: list[Finding] = []
        norm_index = _norm_hash_index(knowledge)

        blocks = [
            b for b in enumerate_code_blocks(page.body, line_offset=page.body_offset)
            if b.content.strip()
            and b.canonical_lang not in NON_EXECUTABLE_LANGS
            and b.canonical_lang not in _SHELL_LANGS
        ]
        if not blocks:
            return findings

        if not norm_index:
            findings.append(Finding(
                level="INFO", category="EX", filepath=str(page.filepath), line_no=0,
                message=(
                    "Example execution proof lookup SKIPPED: this product's snippet "
                    "index has no code_sha256 yet -- run the post-promote proof sweep "
                    "to populate it"
                ),
                evaluator=self.name,
            ))

        deadline = time.monotonic() + _BUDGET_SECONDS
        budget_warned = False

        for block in blocks:
            if time.monotonic() >= deadline:
                if not budget_warned:
                    findings.append(Finding(
                        level="WARN", category="EX", filepath=str(page.filepath),
                        line_no=block.start_line,
                        message=(
                            "Example execution budget exhausted for this page -- "
                            "remaining blocks NOT-VERIFIED: BUDGET-EXHAUSTED"
                        ),
                        evaluator=self.name,
                    ))
                    budget_warned = True
                continue

            if norm_index:
                status, entry = _lookup_proof(
                    norm_index.get(block.sha256_norm), page.family, page.platform)
                if status == "inherited":
                    proof = entry["execution_proof"]
                    findings.append(Finding(
                        level="INFO", category="EX", filepath=str(page.filepath),
                        line_no=block.start_line,
                        message=(
                            f"Verified via snippet {entry.get('id', '?')} "
                            f"(tier {proof.get('tier')}, inherited)"
                        ),
                        evaluator=self.name,
                    ))
                elif status == "stale_by":
                    findings.append(Finding(
                        level="WARN", category="EX", filepath=str(page.filepath),
                        line_no=block.start_line,
                        message=(
                            f"Matches snippet {entry.get('id', '?')} but its execution "
                            "proof is stale"
                        ),
                        evaluator=self.name,
                    ))
                else:
                    findings.append(Finding(
                        level="WARN", category="EX", filepath=str(page.filepath),
                        line_no=block.start_line,
                        message="Novel code block with no verified execution proof on record",
                        evaluator=self.name,
                    ))

            result = check_syntax(block.canonical_lang or block.lang, block.content)
            if result.status == "SYNTAX-ERROR":
                # block.start_line is the opening fence line itself (e.g. the
                # ```python line), so content line 1 is start_line + 1 --
                # result.error_line is already 1-based within the content.
                error_line = block.start_line + (result.error_line or 1)
                findings.append(Finding(
                    level="FAIL", category="EX", filepath=str(page.filepath),
                    line_no=error_line,
                    message=f"Example execution: {result.message}",
                    evaluator=self.name,
                ))
            elif result.status == "GRAMMAR-UNAVAILABLE":
                findings.append(Finding(
                    level="WARN", category="EX", filepath=str(page.filepath),
                    line_no=block.start_line,
                    message=f"Example execution: {result.message}",
                    evaluator=self.name,
                ))

        return findings
