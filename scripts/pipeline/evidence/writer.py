"""writer.py — Write evidence block into file frontmatter (atomic, style-preserving).

Extracted from attach_evidence.py (Phase 5). Merges the evidence: block into
the page's YAML frontmatter using text-level surgery — the full frontmatter is
never round-tripped through yaml.dump, so all original YAML scalar styles
(literal block |, folded >, quoted, unquoted) are preserved byte-for-byte.

Background: PyYAML's yaml.safe_load discards scalar style information. A subsequent
yaml.dump picks its own heuristics — long code-containing strings become double-quoted
with \\n escapes, or single-quoted multi-line flow scalars with indented continuations.
Either form can cause rendering differences in Hugo/goldmark for code blocks that were
originally authored as clean | literal block scalars.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.fs import atomic_write  # noqa: E402

from core.markdown import _FRONTMATTER_WRITER_RE as _FRONTMATTER_RE

# Matches the evidence: key and all its indented child lines.
# Anchored at start-of-line (MULTILINE). Stops at the first line that starts
# without whitespace (next top-level key) or end of string.
# Handles both block-style (evidence:\n  key: val) and inline (evidence: {}).
_EVIDENCE_BLOCK_RE = re.compile(
    r"^evidence:[ \t]*(?:\n[ \t]+[^\n]*)*",
    re.MULTILINE,
)


def _log(*args, **kwargs):
    import sys as _sys
    print(*args, file=_sys.stderr, **kwargs)


def _extract_existing_claims(fm_text: str) -> list:
    """Extract the claims list from an existing evidence block in frontmatter text.

    Parses only the evidence sub-block via yaml.safe_load — never the full
    frontmatter — so no scalar-style information is disturbed.
    """
    import yaml

    m = _EVIDENCE_BLOCK_RE.search(fm_text)
    if not m:
        return []
    try:
        parsed = yaml.safe_load(m.group(0))
        if not isinstance(parsed, dict):
            return []
        # parsed is either {'evidence': {...}} or the inner dict directly
        inner = parsed.get("evidence", parsed)
        if isinstance(inner, dict):
            return list(inner.get("claims", []))
    except Exception:
        pass
    return []


def _extract_existing_apis(fm_text: str) -> list:
    """Extract the apis list from an existing evidence block in frontmatter text.

    Mirrors _extract_existing_claims. Used to preserve metadata-derived apis
    (e.g. from batch_reference.py) when code-token extraction yields nothing.
    """
    import yaml

    m = _EVIDENCE_BLOCK_RE.search(fm_text)
    if not m:
        return []
    try:
        parsed = yaml.safe_load(m.group(0))
        if not isinstance(parsed, dict):
            return []
        inner = parsed.get("evidence", parsed)
        if isinstance(inner, dict):
            return list(inner.get("apis", []))
    except Exception:
        pass
    return []


def _build_evidence_yaml(evidence_dict: dict) -> str:
    """Serialize just the evidence: block to a YAML string.

    This is safe because evidence contains only simple scalars and lists of
    strings — no multi-line code-block content. PyYAML produces clean output.

    Note: yaml.dump emits blank lines between complex sequence items (e.g. sections
    entries that contain nested formats dicts). Those blank lines would break
    _EVIDENCE_BLOCK_RE on subsequent runs because the regex stops at blank lines.
    We collapse consecutive blank lines to single newlines to keep the block
    regex-matchable across re-runs (idempotency fix for RG-001).
    """
    import re
    import yaml

    raw = yaml.dump(
        {"evidence": evidence_dict},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    # Collapse consecutive blank lines that yaml.dump inserts between complex
    # list items.  A single trailing newline is preserved.
    return re.sub(r"\n{2,}", "\n", raw)


def _write_evidence_to_frontmatter(filepath, evidence_dict) -> bool:
    """Merge evidence: block into the file's YAML frontmatter. Creates block if absent.

    Key invariant: every byte outside the evidence: block is preserved exactly.
    No yaml.safe_load + yaml.dump round-trip is performed on the full frontmatter.

    Note: this function does NOT call update_mechanism / set last_mechanism.
    Evidence attachment is a metadata-only operation; its timing is implicit from
    the evidence block's presence in the frontmatter.

    Returns True on success, False on skip/error.
    """
    # utf-8-sig strips a leading BOM if present. A BOM makes the anchored
    # frontmatter regex fail to match even on an otherwise well-formed file,
    # which used to fall through to the "no frontmatter" branch below and
    # corrupt the file with a duplicate, evidence-only frontmatter block
    # (see the malformed-frontmatter guard note for the full failure mode).
    # atomic_write() always writes plain utf-8, so any BOM is stripped on
    # output — this is intentional, not incidental.
    text = filepath.read_text(encoding="utf-8-sig")
    m = _FRONTMATTER_RE.match(text)

    if m:
        open_fence, fm_text, close_fence = m.group(1), m.group(2), m.group(3)
        body = text[m.end():]

        # Merge claims: read from existing evidence block only (no full YAML parse).
        # When the runner supplies the current knowledge claim set, preserve only
        # existing manual claims that still exist in that model. This keeps manual
        # evidence stable without carrying orphan claim IDs across refreshes.
        valid_claim_ids = evidence_dict.pop("_valid_claim_ids", None)
        existing_claims = _extract_existing_claims(fm_text)
        if valid_claim_ids is not None:
            existing_claims = [c for c in existing_claims if c in valid_claim_ids]
        merged_claims = sorted(set(
            existing_claims + list(evidence_dict.get("claims", []))
        ))
        # Merge apis: preserve metadata-derived apis (e.g. from batch_reference.py)
        # when code-token extraction yields nothing. Both sources are valid —
        # metadata-derived (class members) and code-extracted (token scan).
        existing_apis = _extract_existing_apis(fm_text)
        merged_apis = sorted(set(
            existing_apis + list(evidence_dict.get("apis", []))
        ))
        evidence_dict = {**evidence_dict, "claims": merged_claims, "apis": merged_apis}

        evidence_yaml = _build_evidence_yaml(evidence_dict)

        if _EVIDENCE_BLOCK_RE.search(fm_text):
            # Surgical replace: substitute only the evidence block, touch nothing else
            new_fm = _EVIDENCE_BLOCK_RE.sub(evidence_yaml.rstrip("\n"), fm_text)
        else:
            # Append: add evidence block after the last line of existing frontmatter
            new_fm = fm_text.rstrip("\n") + "\n" + evidence_yaml

        new_text = f"{open_fence}{new_fm}{close_fence}{body}"

    else:
        # Regex did not match.  Before prepending a new block, guard against
        # the case where the file already starts with --- (valid frontmatter
        # whose closing fence lacked a trailing newline, or otherwise
        # malformed).  Prepending in that case would create double frontmatter,
        # which Hugo silently ignores — a silent data-loss corruption.
        # Strip common invisible leading characters (BOM, zero-width space,
        # ordinary whitespace) before checking for a leading fence — a bare
        # str.lstrip() does not strip "﻿", so a BOM'd file with malformed
        # frontmatter would otherwise slip past this guard undetected.
        if text.lstrip("﻿​ \t\r\n").startswith("---"):
            raise ValueError(
                f"Frontmatter regex failed on {filepath} but file starts with "
                "'---'.  The file likely has malformed frontmatter (e.g. missing "
                "trailing newline after closing fence).  Refusing to prepend a "
                "new block to avoid double-frontmatter corruption.  Fix the "
                "source file and retry."
            )
        # Genuinely no frontmatter — prepend a minimal one containing only evidence.
        # Pop _valid_claim_ids first (mirrors the pop in the matched branch above,
        # line ~141) — it is an internal validation set, never meant to be
        # serialized into the file itself.
        evidence_dict.pop("_valid_claim_ids", None)
        evidence_yaml = _build_evidence_yaml(evidence_dict)
        new_text = f"---\n{evidence_yaml}---\n\n{text}"

    atomic_write(filepath, new_text)

    return True
