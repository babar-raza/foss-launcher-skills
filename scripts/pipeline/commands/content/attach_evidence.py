"""Deterministic evidence block generator for content pages.

Builds the `evidence:` frontmatter block by extracting verified API tokens
from code blocks and mapping them to claim_ids via the knowledge model index.
No LLM required. Same inputs → same outputs on every run.

Usage:
    python scripts/pipeline/attach_evidence.py 3d python          # one product
    python scripts/pipeline/attach_evidence.py all                 # all products
    python scripts/pipeline/attach_evidence.py --files path1.md   # specific files
    python scripts/pipeline/attach_evidence.py 3d python --dry-run # preview, no writes

Rules:
    - Pages with audit FAIL findings are skipped (evidence only attests verified content)
    - Pages that already have evidence: with the current model_sha are skipped (idempotent)
    - Prose-only pages (no code blocks) get evidence: with claims: [], apis: [] — honest gap
    - Existing evidence: block is merged, not replaced (existing manual claims are preserved)
    - Per-section evidence breakdown via `sections:` array (backward-compatible)
"""
import json
import re
import sys
from pathlib import Path

# Reuse all machinery from audit.py
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# --- Standalone repo path resolution via config_loader ---
_HERE = Path(__file__).resolve().parent          # scripts/pipeline/
_SCRIPTS = _HERE.parent                          # scripts/
import sys as _sys
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))
from config_loader import (                       # noqa: E402
    resolve_content_repo as _resolve_content_repo,
    resolve_reports_root as _resolve_reports_root,
    resolve_knowledge_root as _resolve_knowledge_root,
)
# --------------------------------------------------------

from knowledge_core import (  # noqa: E402
    Knowledge,
    KNOWLEDGE_ROOT,
    LOCALE_RE,
    discover_content,
    discover_products,
    infer_product,
    parse_frontmatter,
)
from token_ops import (  # noqa: E402
    PLATFORM_SDK_CLASSES,
    PROPERTY_CHAIN_CLASSES,
    extract_tokens,
    verify_tokens,
)

_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_CODE_FENCE_RE = re.compile(r"^```(\w*)")


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


# Internal implementation class names extracted by scout that are not user-facing formats.
# These appear in formats.json as exporter base/registry/factory classes and must be excluded.
_INTERNAL_FORMAT_NAMES = frozenset({"base", "registry", "factory", "pptxfactory"})

# Maximum length for a plausible file extension (e.g. "docx"=4, "pptx"=4, "html"=4, "jpeg"=4)
_MAX_EXT_LEN = 8


# ---------------------------------------------------------------------------
# Section parsing — split body into heading-delimited sections
# ---------------------------------------------------------------------------
def _parse_sections(filepath):
    """Split the markdown body into sections delimited by H2/H3 headings.

    Returns a list of dicts:
        [{"heading": str, "level": int, "line": int,
          "body_lines": [(line_no, text), ...],
          "code_ranges": [(start, end), ...]}, ...]

    Content before the first heading is assigned heading="Introduction", line=1.
    """
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Skip frontmatter
    body_start = 0
    fm_match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if fm_match:
        body_start = text[:fm_match.end()].count("\n")

    sections = []
    current = {
        "heading": "Introduction",
        "level": 1,
        "line": 1,
        "body_lines": [],
        "code_ranges": [],
    }

    in_code = False
    code_start = 0

    for idx in range(body_start, len(lines)):
        line_no = idx + 1  # 1-based
        line = lines[idx]
        stripped = line.strip()

        # Code fence toggle
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_start = line_no
            else:
                current["code_ranges"].append((code_start, line_no))
                in_code = False
            current["body_lines"].append((line_no, line))
            continue

        if in_code:
            current["body_lines"].append((line_no, line))
            continue

        # Heading detection (H2/H3 are section boundaries)
        hm = _HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            if level <= 3:
                # Flush current section
                sections.append(current)
                current = {
                    "heading": hm.group(2).strip(),
                    "level": level,
                    "line": line_no,
                    "body_lines": [],
                    "code_ranges": [],
                }
                continue

        current["body_lines"].append((line_no, line))

    # Flush last section
    sections.append(current)

    return sections


# ---------------------------------------------------------------------------
# Per-section token extraction
# ---------------------------------------------------------------------------
def _extract_section_tokens(filepath, section, platform):
    """Extract API tokens from a single section's code blocks.

    We re-use audit.py's extract_tokens on the full file but filter by
    line ranges belonging to this section's code blocks.
    """
    all_tokens = extract_tokens(filepath, platform)

    # Build line ranges for this section's code blocks
    code_ranges = section["code_ranges"]
    if not code_ranges:
        return []

    section_tokens = []
    for tok in all_tokens:
        for start, end in code_ranges:
            if start <= tok.line_no <= end:
                section_tokens.append(tok)
                break

    return section_tokens


def _section_has_code_blocks(section):
    """Return True if section contains at least one code block."""
    return len(section["code_ranges"]) > 0


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------
def _load_known_formats(knowledge):
    """Load and normalise known formats from formats.json."""
    formats_path = _resolve_knowledge_root() / knowledge.family / knowledge.platform / "merged" / "formats.json"
    if not formats_path.exists():
        return []

    known_formats = json.loads(formats_path.read_text(encoding="utf-8"))
    if not isinstance(known_formats, list):
        return []

    result = []
    for entry in known_formats:
        if not isinstance(entry, dict):
            continue
        ext = entry.get("extension", entry.get("ext", entry.get("format", ""))).lower().lstrip(".")
        if not ext or ext in _INTERNAL_FORMAT_NAMES or len(ext) > _MAX_EXT_LEN:
            continue
        support = entry.get("support", entry.get("direction", ""))
        result.append({"ext": ext, "support": support})
    return result


def _detect_formats(filepath, knowledge):
    """Scan page body for format extension mentions; cross-ref against formats.json.

    Normalises field names: accepts ``extension``, ``ext``, or ``format`` as the
    extension key, and ``support`` or ``direction`` as the support key.  Filters
    out internal implementation class names (Base, Registry, PptxFactory, …) that
    scout may emit into formats.json but that are not user-facing file formats.
    """
    known = _load_known_formats(knowledge)
    if not known:
        return []

    text = filepath.read_text(encoding="utf-8").lower()
    result = []
    seen_exts = set()
    for entry in known:
        ext = entry["ext"]
        if ext in seen_exts:
            continue
        if re.search(rf'\.{re.escape(ext)}\b|(?<![a-z]){re.escape(ext)}(?![a-z])', text):
            result.append(entry)
            seen_exts.add(ext)
    return result


def _detect_formats_in_text(text, knowledge):
    """Detect format references within a text string (for per-section detection)."""
    known = _load_known_formats(knowledge)
    if not known:
        return []

    text_lower = text.lower()
    result = []
    seen_exts = set()
    for entry in known:
        ext = entry["ext"]
        if ext in seen_exts:
            continue
        if re.search(rf'\.{re.escape(ext)}\b|(?<![a-z]){re.escape(ext)}(?![a-z])', text_lower):
            result.append(entry)
            seen_exts.add(ext)
    return result


# ---------------------------------------------------------------------------
# Token → claim/api mapping (shared logic)
# ---------------------------------------------------------------------------
def _map_tokens_to_evidence(tokens, knowledge):
    """Map a list of tokens to claim_ids and api_refs.

    Returns (claim_ids: list[str], api_refs: list[str]).
    """
    claim_ids = []
    api_refs = []
    seen_refs = set()

    for tok in tokens:
        if tok.kind in ("import", "table_member"):
            continue
        cls = tok.class_name
        if not cls or cls not in knowledge.classes:
            continue
        if cls in PLATFORM_SDK_CLASSES or cls in PROPERTY_CHAIN_CLASSES:
            continue
        member = tok.member_name if tok.member_name and tok.member_name != "__init__" else None
        if member and not knowledge.has_method(cls, member) \
                and not knowledge.has_property(cls, member) \
                and not knowledge.has_enum_member(cls, member):
            member = None

        ref = f"{cls}.{member}" if member else cls
        if ref in seen_refs:
            continue
        seen_refs.add(ref)

        api_key = f"{cls}.{tok.member_name}" if tok.member_name else cls
        cid = knowledge.api_to_claim.get(api_key)
        if cid:
            claim_ids.append(cid)
        if member:
            api_refs.append(f"{cls}.{member}")

    return claim_ids, api_refs


# ---------------------------------------------------------------------------
# Build per-section evidence entries
# ---------------------------------------------------------------------------
def _build_sections_evidence(filepath, knowledge):
    """Build the sections array for paragraph-level evidence.

    Returns a list of section evidence dicts (only sections with evidence).
    """
    sections = _parse_sections(filepath)
    platform = knowledge.platform
    result = []

    for section in sections:
        # Extract tokens for this section
        section_tokens = _extract_section_tokens(filepath, section, platform)
        claim_ids, api_refs = _map_tokens_to_evidence(section_tokens, knowledge)

        # Detect format references in this section's text
        section_text = "\n".join(text for _, text in section["body_lines"])
        formats = _detect_formats_in_text(section_text, knowledge)

        # Skip sections with no evidence
        if not claim_ids and not api_refs and not formats:
            continue

        entry = {
            "heading": section["heading"],
            "line": section["line"],
            "claims": sorted(set(claim_ids)),
            "apis": sorted(set(api_refs)),
        }
        if formats:
            entry["formats"] = formats

        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# Frontmatter writer
# ---------------------------------------------------------------------------
def _write_evidence_to_frontmatter(filepath, evidence_dict):
    """Merge evidence: block into the file's YAML frontmatter. Creates block if absent."""
    import yaml

    text = filepath.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)

    if m:
        open_fence, fm_text, close_fence = m.group(1), m.group(2), m.group(3)
        body = text[m.end():]
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            _log(f"  SKIP {filepath}: malformed frontmatter YAML")
            return False

        # Merge: preserve any existing keys; only update evidence:
        existing = fm.get("evidence") or {}
        if isinstance(existing, dict):
            # Preserve manually added claims not in our detected set
            merged_claims = sorted(set(existing.get("claims", []) + evidence_dict.get("claims", [])))
            evidence_dict["claims"] = merged_claims
        fm["evidence"] = evidence_dict

        new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
        new_text = f"{open_fence}{new_fm}{close_fence}{body}"
    else:
        # No frontmatter — prepend one
        import yaml
        new_fm = yaml.dump({"evidence": evidence_dict}, default_flow_style=False,
                           allow_unicode=True, sort_keys=False)
        new_text = f"---\n{new_fm}---\n\n{text}"

    filepath.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Core attachment logic
# ---------------------------------------------------------------------------
def attach_evidence(filepath, knowledge, dry_run=False, force=False):
    """Build and write evidence block for one file. Returns status string."""
    fm = parse_frontmatter(filepath)
    existing = fm.get("evidence") or {}

    # Already up to date — idempotent skip (bypass with --force)
    if not force and isinstance(existing, dict) and existing.get("model_sha") == knowledge.repo_sha:
        return "SKIP (current)"

    platform = knowledge.platform

    # Extract and verify API tokens (page-level)
    tokens = extract_tokens(filepath, platform)
    findings = verify_tokens(tokens, knowledge, filepath)
    fails = [f for f in findings if f.level == "FAIL"]
    if fails:
        _log(f"  SKIP {filepath}: {len(fails)} audit FAIL(s) — fix before attaching evidence")
        return "SKIP (audit FAILs)"

    # Map verified tokens → claim_ids via deterministic index (aggregate)
    claim_ids, api_refs = _map_tokens_to_evidence(tokens, knowledge)

    # Detect format references (page-level aggregate)
    formats = _detect_formats(filepath, knowledge)

    # Build per-section evidence breakdown
    sections = _build_sections_evidence(filepath, knowledge)

    evidence = {
        "model_sha": knowledge.repo_sha,
        "model_version": knowledge.version,
        "claims": sorted(set(claim_ids)),
        "apis": sorted(set(api_refs)),
    }
    if formats:
        evidence["formats"] = formats
    if sections:
        evidence["sections"] = sections

    if dry_run:
        _log(f"  DRY-RUN {filepath}:")
        _log(f"    claims: {len(evidence['claims'])}, apis: {len(evidence['apis'])}, "
             f"formats: {len(formats)}, sections: {len(sections)}")
        for sec in sections:
            _log(f"      [{sec['line']}] {sec['heading']}: "
                 f"claims={len(sec['claims'])}, apis={len(sec['apis'])}")
        return "DRY-RUN"

    ok = _write_evidence_to_frontmatter(filepath, evidence)
    return "UPDATED" if ok else "ERROR"


# ---------------------------------------------------------------------------
# Batch runners
# ---------------------------------------------------------------------------
def attach_product(family, platform, dry_run=False, force=False):
    """Attach evidence to all content files for a product."""
    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        _log(f"  SKIP {family}/{platform}: no knowledge model")
        return {}

    files = discover_content(family, platform)
    if not files:
        _log(f"  SKIP {family}/{platform}: no content files")
        return {}

    _log(f"  {family}/{platform}: {len(files)} files")
    counts = {"UPDATED": 0, "SKIP (current)": 0, "SKIP (audit FAILs)": 0,
              "DRY-RUN": 0, "ERROR": 0}
    for f in files:
        status = attach_evidence(f, knowledge, dry_run=dry_run, force=force)
        counts[status] = counts.get(status, 0) + 1

    _log(f"    -> {counts}")
    return counts


def attach_files(file_paths, dry_run=False, force=False):
    """Attach evidence to specific files."""
    knowledge_cache = {}
    counts = {}
    for fp in file_paths:
        fp = Path(fp)
        if not fp.exists():
            _log(f"  SKIP {fp}: not found")
            continue
        family, platform = infer_product(fp)
        if not family:
            _log(f"  SKIP {fp}: cannot infer product")
            continue
        key = (family, platform)
        if key not in knowledge_cache:
            knowledge_cache[key] = Knowledge(family, platform)
        knowledge = knowledge_cache[key]
        if not knowledge.available:
            _log(f"  SKIP {fp}: no knowledge for {family}/{platform}")
            continue
        status = attach_evidence(fp, knowledge, dry_run=dry_run, force=force)
        counts[status] = counts.get(status, 0) + 1
    _log(f"  -> {counts}")
    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _auto_refresh(family, platform):
    """Run refresh_knowledge.py for a product if --auto-refresh is set."""
    import subprocess
    script = Path(__file__).parent / "refresh_knowledge.py"
    if not script.exists():
        _log(f"  WARNING: refresh_knowledge.py not found, skipping auto-refresh")
        return
    _log(f"  Auto-refreshing knowledge for {family}/{platform}...")
    result = subprocess.run(
        [sys.executable, str(script), family, platform],
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    if result.returncode != 0:
        _log(f"  WARNING: refresh_knowledge.py failed (exit {result.returncode}), continuing with existing knowledge")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args
    files_mode = "--files" in args
    auto_refresh = "--auto-refresh" in args
    args = [a for a in args if not a.startswith("--")]

    if files_mode:
        _log("Attaching evidence to specified files...")
        attach_files(args, dry_run=dry_run, force=force)
    elif len(args) >= 2:
        family, platform = args[0], args[1]
        if auto_refresh:
            _auto_refresh(family, platform)
        _log(f"Attaching evidence for {family}/{platform}...")
        attach_product(family, platform, dry_run=dry_run, force=force)
    elif len(args) == 1 and args[0] == "all":
        products = discover_products()
        _log(f"Attaching evidence for {len(products)} products...")
        total = {}
        for family, platform in products:
            if auto_refresh:
                _auto_refresh(family, platform)
            counts = attach_product(family, platform, dry_run=dry_run, force=force)
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
        _log(f"\nTotal: {total}")
    else:
        # Use sys.stdout.buffer.write for Windows cp1252 compatibility
        doc = (__doc__ or "").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(doc + b"\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
