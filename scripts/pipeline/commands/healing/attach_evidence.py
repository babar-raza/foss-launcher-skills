"""Deterministic evidence block generator for content pages.

Builds the `evidence:` frontmatter block by extracting verified API tokens
from code blocks and mapping them to claim_ids via the knowledge model index.
No LLM required. Same inputs → same outputs on every run.

Usage:
    python scripts/pipeline/commands/healing/attach_evidence.py 3d python          # one product
    python scripts/pipeline/commands/healing/attach_evidence.py all                 # all products
    python scripts/pipeline/commands/healing/attach_evidence.py --files path1.md   # specific files
    python scripts/pipeline/commands/healing/attach_evidence.py 3d python --dry-run # preview, no writes

Rules:
    - Pages with audit FAIL findings are skipped (evidence only attests verified content)
    - Pages that already have evidence: with the current model_sha are skipped (idempotent)
    - Prose-only pages (no code blocks) get evidence: with claims: [], apis: [] — honest gap
    - Existing evidence: block is merged, not replaced (existing manual claims are preserved)
    - Per-section evidence breakdown via `sections:` array (backward-compatible)
    - MT074 B13b: before any (non dry-run) attach, citations of RE-IDENTIFIED claims are
      restamped old-id -> new-id from knowledge_delta.json `reidentified_claims`, so a claim
      whose id changed but whose text did not is not pruned as an orphan citation.

Implementation is in the evidence/ package (Phase 5 refactor); this file keeps the CLI
entry point plus the (additive) re-identified-claim restamp pre-pass.
Import from `evidence` to get all symbols — Python loads evidence/__init__.py
when the package exists alongside this file.
"""
# All attach implementation lives in evidence/ sub-modules.
import json
import sys
from pathlib import Path

# cli-entry-point guard: _HERE = commands/healing; .parent.parent = scripts/pipeline (where evidence/ lives)
_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent  # scripts/pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from evidence.runner import main as _runner_main  # noqa: E402


# ---------------------------------------------------------------------------
# MT074 B13b -- restamp evidence citations of re-identified claims
# ---------------------------------------------------------------------------
#
# Why: claim ids for non-member claims derive from LLM wording (enrich._assign_ids), so a
# rebuild can re-ID a claim without changing its text.  refresh_knowledge's
# _write_knowledge_delta records those as `reidentified_claims` {old_id: new_id}.  The
# evidence writer prunes every existing cited id that is not in the current claim set, so
# without this pass a re-ID'd claim's citations silently become orphans (and then look like
# "removed content" to every downstream consumer).  This pass rewrites the ids FIRST; the
# normal attach then sees valid ids and keeps them.


def load_reidentified_claims(knowledge_root, family: str, platform: str) -> dict:
    """Return {old_claim_id: new_claim_id} from the product's knowledge_delta.json
    (empty when the delta is absent/unreadable or records none).  Only mappings whose new
    id exists in the current merged/claims.json are returned, so a restamp can never
    create a fresh orphan."""
    merged = Path(knowledge_root) / family / platform / "merged"
    try:
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = delta.get("reidentified_claims") if isinstance(delta, dict) else None
    if not isinstance(raw, dict) or not raw:
        return {}
    mapping = {str(k): str(v) for k, v in raw.items() if k and v and k != v}
    if not mapping:
        return {}
    try:
        claims = json.loads((merged / "claims.json").read_text(encoding="utf-8"))
        claims = claims if isinstance(claims, list) else claims.get("claims", [])
        valid = {c.get("claim_id") for c in claims if isinstance(c, dict)}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}
    return {old: new for old, new in mapping.items() if new in valid}


def _map_claim_list(claims, mapping: dict):
    """Map ids in a claims list; dedupe preserving order. Returns (new_list, changed)."""
    if not isinstance(claims, list):
        return claims, False
    out, seen, changed = [], set(), False
    for cid in claims:
        new = mapping.get(cid, cid) if isinstance(cid, str) else cid
        if new != cid:
            changed = True
        if isinstance(new, str):
            if new in seen:
                changed = True
                continue
            seen.add(new)
        out.append(new)
    return out, changed


def restamp_reidentified_in_text(text: str, mapping: dict) -> "tuple[str, int]":
    """Rewrite re-identified claim ids inside the page's evidence block (top-level
    ``claims`` and every ``sections[*].claims``).  Everything outside the evidence block
    is left byte-for-byte untouched.  Returns (new_text, number_of_ids_restamped)."""
    import yaml
    from evidence.writer import _EVIDENCE_BLOCK_RE, _FRONTMATTER_RE, _build_evidence_yaml

    if not mapping:
        return text, 0
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, 0
    open_fence, fm_text, close_fence = m.group(1), m.group(2), m.group(3)
    block = _EVIDENCE_BLOCK_RE.search(fm_text)
    if not block:
        return text, 0
    try:
        parsed = yaml.safe_load(block.group(0))
    except yaml.YAMLError:
        return text, 0
    evidence = parsed.get("evidence") if isinstance(parsed, dict) else None
    if not isinstance(evidence, dict):
        return text, 0

    restamped = 0
    new_claims, changed = _map_claim_list(evidence.get("claims"), mapping)
    if changed:
        restamped += sum(1 for c in (evidence.get("claims") or []) if c in mapping)
        evidence["claims"] = sorted(new_claims, key=str)
    sections = evidence.get("sections")
    if isinstance(sections, list):
        for sec in sections:
            if isinstance(sec, dict) and "claims" in sec:
                sec_claims, sec_changed = _map_claim_list(sec.get("claims"), mapping)
                if sec_changed:
                    restamped += sum(1 for c in (sec.get("claims") or []) if c in mapping)
                    sec["claims"] = sorted(sec_claims, key=str)
    if not restamped:
        return text, 0
    new_block = _build_evidence_yaml(evidence).rstrip("\n")
    new_fm = fm_text[:block.start()] + new_block + fm_text[block.end():]
    return f"{open_fence}{new_fm}{close_fence}{text[m.end():]}", restamped


def restamp_reidentified(files, mapping: dict, *, dry_run: bool = False, gate_fn=None) -> dict:
    """Restamp re-identified claim citations in each file.  Returns
    {"files_changed", "ids_restamped", "skipped_draft", "skipped_gate"}.
    Writes atomically, never raises per file.

    Same per-page gates as the runner's attach: a ``draft: true`` page is never touched,
    and ``gate_fn(path) -> bool`` (the audit-FAIL gate) must pass.  Both are evaluated
    only for a page that actually cites a re-identified id, so the common page costs a
    read and a regex."""
    from core.fs import atomic_write
    from core.markdown import parse_frontmatter

    result = {"files_changed": 0, "ids_restamped": 0, "skipped_draft": 0, "skipped_gate": 0}
    if not mapping:
        return result
    for fp in files:
        fp = Path(fp)
        try:
            text = fp.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        new_text, n = restamp_reidentified_in_text(text, mapping)
        if not n:
            continue
        if parse_frontmatter(fp).get("draft") is True:
            result["skipped_draft"] += 1
            continue
        if gate_fn is not None and not gate_fn(fp):
            result["skipped_gate"] += 1
            continue
        result["files_changed"] += 1
        result["ids_restamped"] += n
        if not dry_run:
            atomic_write(fp, new_text)
    return result


def _default_audit_gate(family: str, platform: str):
    """The runner's audit-FAIL gate (extract + verify tokens; a FAIL page is skipped by
    attach, so its citations are not restamped either).  None => product has no knowledge
    model, nothing can be restamped."""
    import evidence.runner as R

    knowledge = (R._cfg_knowledge_fn or R.Knowledge)(family, platform)
    if not getattr(knowledge, "available", False):
        return lambda fp: False
    extract = R._cfg_extract_tokens_fn or R.extract_tokens
    verify = R._cfg_verify_tokens_fn or R.verify_tokens

    def gate(fp) -> bool:
        findings = verify(extract(fp, platform), knowledge, fp)
        return not any(f.level == "FAIL" for f in findings)
    return gate


def _default_version_jump_refused(family: str, platform: str) -> bool:
    """Mirror of attach_product's bulk --force model_version-jump refusal (TC-SFH-007)."""
    import evidence.runner as R

    knowledge = (R._cfg_knowledge_fn or R.Knowledge)(family, platform)
    if not getattr(knowledge, "available", False):
        return False
    stamped = R._sample_stamped_model_version(family, platform)
    return stamped is not None and R._is_model_version_jump(stamped, knowledge.version)


def _pre_restamp(argv: list, *, knowledge_root=None, audit_gate_factory=None,
                 version_jump_refused=None, discover_fn=None) -> dict:
    """Run the restamp pre-pass for whatever product(s)/file(s) `argv` targets.

    Runs ONLY for write modes with a valid target shape (``family platform`` | ``all`` |
    ``--files <paths>``), and honours the runner's gates: --dry-run/--dry-run-json,
    --apply-claim-plan and --detect-stale-claims (incl. --report-json) and -h/--help are
    no-ops; --subdomain filters; draft pages and audit-FAIL pages are skipped; a bulk
    --force over a model_version jump (without --confirm-model-version-jump) is refused
    exactly as attach_product refuses it.  ``--max-files`` caps only --apply-claim-plan
    (see runner.main), which this pass never runs for, so there is no cap to apply."""
    import argparse
    from collections import defaultdict
    import content_discovery as cd  # noqa: E402

    empty = {"files_changed": 0, "ids_restamped": 0, "skipped_draft": 0, "skipped_gate": 0}
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("args", nargs="*")
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("--files", action="store_true")
    parser.add_argument("--subdomain")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dry-run-json")
    parser.add_argument("--apply-claim-plan")
    parser.add_argument("--detect-stale-claims", action="store_true")
    parser.add_argument("--report-json")
    parser.add_argument("--max-files")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--all-subdomains", action="store_true")
    parser.add_argument("--confirm-all-subdomains", action="store_true")
    parser.add_argument("--confirm-model-version-jump", action="store_true")
    parser.add_argument("--auto-refresh", action="store_true")
    parser.add_argument("--confirm-apply", action="store_true")
    try:
        ns, _unknown = parser.parse_known_args(argv)
    except SystemExit:
        return empty
    if (ns.help or ns.dry_run or ns.dry_run_json or ns.apply_claim_plan
            or ns.detect_stale_claims or ns.report_json):
        return empty

    kroot = Path(knowledge_root) if knowledge_root is not None else cd.KNOWLEDGE_ROOT
    by_product: dict = defaultdict(list)
    if ns.files:
        for raw in ns.args:
            fp = Path(raw)
            fam, plat = cd.infer_product(fp)
            if fam:
                by_product[(fam, plat)].append(fp)
    elif len(ns.args) >= 2:
        by_product[(ns.args[0], ns.args[1])] = None
    elif len(ns.args) == 1 and ns.args[0] == "all":
        for prod in cd.discover_products():
            by_product[prod] = None
    else:
        return empty

    gate_factory = audit_gate_factory or _default_audit_gate
    jump_refused = version_jump_refused or _default_version_jump_refused
    discover = discover_fn or cd.discover_content
    total = dict(empty)
    for (fam, plat), files in by_product.items():
        mapping = load_reidentified_claims(kroot, fam, plat)
        if not mapping:
            continue
        if files is None:
            if ns.force and not ns.confirm_model_version_jump and jump_refused(fam, plat):
                print(f"  restamp {fam}/{plat}: skipped -- bulk --force over a model_version "
                      f"jump is refused (same gate as attach)", file=sys.stderr)
                continue
            files = discover(fam, plat)
            if ns.subdomain:
                files = [f for f in files if cd._infer_subdomain(f) == ns.subdomain]
        res = restamp_reidentified(files, mapping, gate_fn=gate_factory(fam, plat))
        if res["ids_restamped"]:
            print(f"  restamp {fam}/{plat}: {res['ids_restamped']} re-identified claim "
                  f"citation(s) in {res['files_changed']} file(s)", file=sys.stderr)
        for k in total:
            total[k] += res[k]
    return total


def main() -> None:
    try:
        _pre_restamp(sys.argv[1:])
    except Exception as exc:  # never block evidence attach on the optional pre-pass
        print(f"  WARNING: re-identified-claim restamp skipped ({type(exc).__name__}: {exc})",
              file=sys.stderr)
    _runner_main()


if __name__ == "__main__":
    main()
