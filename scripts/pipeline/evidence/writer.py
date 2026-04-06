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


def _build_evidence_yaml(evidence_dict: dict) -> str:
    """Serialize just the evidence: block to a YAML string.

    This is safe because evidence contains only simple scalars and lists of
    strings — no multi-line code-block content. PyYAML produces clean output.
    """
    import yaml

    return yaml.dump(
        {"evidence": evidence_dict},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def _write_evidence_to_frontmatter(filepath, evidence_dict) -> bool:
    """Merge evidence: block into the file's YAML frontmatter. Creates block if absent.

    Key invariant: every byte outside the evidence: block is preserved exactly.
    No yaml.safe_load + yaml.dump round-trip is performed on the full frontmatter.

    Note: this function does NOT call update_mechanism / set last_mechanism.
    Evidence attachment is a metadata-only operation; its timing is implicit from
    the evidence block's presence in the frontmatter.

    Returns True on success, False on skip/error.
    """
    text = filepath.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)

    if m:
        open_fence, fm_text, close_fence = m.group(1), m.group(2), m.group(3)
        body = text[m.end():]

        # Merge claims: read from existing evidence block only (no full YAML parse)
        existing_claims = _extract_existing_claims(fm_text)
        merged_claims = sorted(set(
            existing_claims + list(evidence_dict.get("claims", []))
        ))
        evidence_dict = {**evidence_dict, "claims": merged_claims}

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
        if text.lstrip().startswith("---"):
            raise ValueError(
                f"Frontmatter regex failed on {filepath} but file starts with "
                "'---'.  The file likely has malformed frontmatter (e.g. missing "
                "trailing newline after closing fence).  Refusing to prepend a "
                "new block to avoid double-frontmatter corruption.  Fix the "
                "source file and retry."
            )
        # Genuinely no frontmatter — prepend a minimal one containing only evidence
        evidence_yaml = _build_evidence_yaml(evidence_dict)
        new_text = f"---\n{evidence_yaml}---\n\n{text}"

    atomic_write(filepath, new_text)

    return True
