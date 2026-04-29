#!/usr/bin/env python3
"""Origin classification for S-43 gap-eval findings.

Annotates each gap-eval finding with its most probable pipeline origin class
and recommended repair route. Classification is deterministic (no LLM calls).

Usage:
    python scripts/gap-eval/src/origin_map.py {gap_eval_json} {family} {platform} [options]

Options:
    --api-surface   Override path to api_surface.json
    --claims        Override path to claims.json
    --out           Output JSON path (default: {input_stem}-origin.json)
    --no-grep       Skip clone-cache grep; classify wrong-api-name as AMBIGUOUS
    --dry-run       Print classifications without writing output

Output fields added to each finding:
    origin_class:              CONTENT | PIPELINE | UPSTREAM | AMBIGUOUS
    origin_subclass:           hallucination | extraction-miss | enrichment-error |
                               profile-stale | planner-gap | broken-link-upstream |
                               low-confidence
    origin_certainty:          HIGH | MEDIUM | LOW
    origin_evidence:           human-readable string of what was checked
    repair_route:              S-26 | S-46 | S-74 | HUMAN-PIPELINE | AMBIGUOUS
    tier3_non_determinism_flag: true | false

Routing safety rule:
    A finding with tier3_non_determinism_flag=True is NEVER placed in the
    CONTENT automation bucket, regardless of origin_class. It goes to the
    pipeline evidence report with a note for the operator to confirm on
    the next run (when tier3_cache is active).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GAP_EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_GAP_EVAL_DIR))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Origin classes
CONTENT = "CONTENT"
PIPELINE = "PIPELINE"
UPSTREAM = "UPSTREAM"
AMBIGUOUS = "AMBIGUOUS"

# Origin subclasses
SUB_HALLUCINATION = "hallucination"
SUB_EXTRACTION_MISS = "extraction-miss"
SUB_ENRICHMENT_ERROR = "enrichment-error"
SUB_PROFILE_STALE = "profile-stale"
SUB_PLANNER_GAP = "planner-gap"
SUB_BROKEN_LINK = "broken-link-upstream"
SUB_LOW_CONFIDENCE = "low-confidence"

# Certainty levels
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# Repair routes
ROUTE_S26 = "S-26"
ROUTE_S46 = "S-46"
ROUTE_S74 = "S-74"
ROUTE_HUMAN = "HUMAN-PIPELINE"
ROUTE_AMBIGUOUS = "AMBIGUOUS"

# Confidence thresholds
_ENRICHMENT_HIGH_CONFIDENCE = 0.7
_ENRICHMENT_LOW_CONFIDENCE = 0.5
_LLM_MIN_CONFIDENCE = 0.6

# Grep timeout (matches stage2_knowledge_validation in run.py)
_GREP_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Knowledge artifact loaders
# ---------------------------------------------------------------------------

def _default_api_surface_path(family: str, platform: str) -> Path:
    return _REPO_ROOT / "knowledge" / family / platform / "merged" / "api_surface.json"


def _default_claims_path(family: str, platform: str) -> Path:
    return _REPO_ROOT / "knowledge" / family / platform / "merged" / "claims.json"


def _default_clone_cache_path(family: str, platform: str) -> Path:
    try:
        sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
        from core.clone_cache import cache_root  # type: ignore  # noqa: PLC0415
        return cache_root() / f"aspose_{family}_{platform}"
    except Exception:
        # Fallback: canonical repo-internal cache (never foss-launcher — that path is obsolete)
        return _REPO_ROOT / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"


def _load_api_surface(path: Path) -> list[dict]:
    if not path.exists():
        log.debug("api_surface.json not found at %s — treating as empty", path)
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Cannot read api_surface.json: %s", exc)
        return []


def _load_claims(path: Path) -> list[dict]:
    if not path.exists():
        log.debug("claims.json not found at %s — treating as empty", path)
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Cannot read claims.json: %s", exc)
        return []


def _build_api_name_set(api_data: list[dict]) -> set[str]:
    """Flat set of all class names + method/property names from api_surface.json."""
    names: set[str] = set()
    for cls in api_data:
        cname = cls.get("name", "")
        if cname:
            names.add(cname)
        for m in cls.get("method_details", []):
            mname = m.get("name", "")
            if mname:
                names.add(f"{cname}.{mname}")
                names.add(mname)
        for p in cls.get("property_details", []):
            pname = p.get("name", "")
            if pname:
                names.add(f"{cname}.{pname}")
                names.add(pname)
    return names


def _find_claim_in_claims(old_value: str, claims: list[dict]) -> dict | None:
    """Search claims.json for an entry whose value fields contain old_value as substring.

    Returns the first matching claim dict, or None if not found.
    """
    needle = old_value.lower()
    for c in claims:
        # Check common claim value field names
        for field in ("value", "description", "identifier", "name", "text"):
            if needle in str(c.get(field, "")).lower():
                return c
    return None


# ---------------------------------------------------------------------------
# Clone cache grep (for wrong-api-name disambiguation)
# ---------------------------------------------------------------------------

def _grep_clone_cache(token: str, clone_cache_path: Path) -> str | None:
    """Search clone cache source files for token.

    Returns: "found" | "not-found" | "error"
    Uses same grep parameters as stage2_knowledge_validation in run.py.
    """
    if not clone_cache_path.exists():
        return "error"
    try:
        result = subprocess.run(
            [
                "grep", "-r",
                "--include=*.java", "--include=*.py", "--include=*.cs",
                "--include=*.ts", "--include=*.cpp", "--include=*.h",
                "-l", token, str(clone_cache_path),
            ],
            capture_output=True, text=True, timeout=_GREP_TIMEOUT,
        )
        if result.returncode == 0 and result.stdout.strip():
            return "found"
        return "not-found"
    except subprocess.TimeoutExpired:
        log.debug("Grep timeout for token '%s' in %s", token, clone_cache_path)
        return "error"
    except FileNotFoundError:
        log.debug("grep not available on this system")
        return "error"
    except Exception as exc:
        log.debug("Grep error for '%s': %s", token, exc)
        return "error"


# ---------------------------------------------------------------------------
# Site plan loader (for missing-section/missing-page classification)
# ---------------------------------------------------------------------------

def _page_in_site_plan(family: str, platform: str, page_path: str) -> bool | None:
    """Return True if page_path appears in site_plan.yaml, False if plan exists but
    page is absent, None if no site_plan.yaml found."""
    plan_path = _REPO_ROOT / "reports" / "plans" / family / platform / "site_plan.yaml"
    if not plan_path.exists():
        return None
    try:
        import yaml  # type: ignore
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    except ImportError:
        log.debug("PyYAML not available — cannot check site_plan.yaml")
        return None
    except Exception as exc:
        log.debug("Cannot read site_plan.yaml: %s", exc)
        return None

    root = plan.get("plan", plan)
    sections = root.get("sections") or {}
    for section_data in sections.values():
        if not isinstance(section_data, dict):
            continue
        for page in section_data.get("pages") or []:
            if isinstance(page, dict) and page.get("path") == page_path:
                return True
    return False


# ---------------------------------------------------------------------------
# Limitations.md checker (for unimplemented-as-working)
# ---------------------------------------------------------------------------

def _token_in_limitations(token: str, family: str, platform: str) -> bool:
    """Return True if token appears in the limitations.md knowledge artifact."""
    lim_path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "limitations.md"
    if not lim_path.exists():
        return False
    try:
        text = lim_path.read_text(encoding="utf-8", errors="replace")
        return token.lower() in text.lower()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------

def _is_tier3_non_deterministic(finding: dict) -> bool:
    """True if this finding came from a live (non-cached) LLM call."""
    return (
        finding.get("tier_resolved_by") == 3
        and not finding.get("tier3_cache_hit", False)
    )


def classify_finding(
    finding: dict,
    family: str,
    platform: str,
    api_names: set[str],
    claims: list[dict],
    clone_cache_path: Path,
    *,
    no_grep: bool = False,
) -> dict:
    """Classify a single finding and return annotation fields.

    Returns a dict with: origin_class, origin_subclass, origin_certainty,
    origin_evidence, repair_route, tier3_non_determinism_flag.
    """
    ftype = finding.get("type", "")
    old_value = finding.get("old_value", "") or ""
    tier = finding.get("tier_resolved_by", 1)
    llm_conf = finding.get("llm_confidence")
    is_non_det = _is_tier3_non_deterministic(finding)

    # Routing safety rule: Tier 3 non-deterministic findings always go to AMBIGUOUS
    # (pipeline evidence) regardless of what other checks find.
    # The note explains this to the operator.
    if is_non_det:
        return {
            "origin_class": AMBIGUOUS,
            "origin_subclass": SUB_LOW_CONFIDENCE,
            "origin_certainty": LOW,
            "origin_evidence": (
                "Tier 3 LLM finding without cache coverage. "
                "Result may differ across reruns. "
                "Confirm after second run with tier3_cache active (no --no-tier3-cache)."
            ),
            "repair_route": ROUTE_AMBIGUOUS,
            "tier3_non_determinism_flag": True,
        }

    # --- broken-link: always UPSTREAM, always S-74 ---
    if ftype == "broken-link":
        return {
            "origin_class": UPSTREAM,
            "origin_subclass": SUB_BROKEN_LINK,
            "origin_certainty": HIGH,
            "origin_evidence": f"Internal link target not found: '{old_value}'. S-74 causal-backtrack handles this.",
            "repair_route": ROUTE_S74,
            "tier3_non_determinism_flag": False,
        }

    # --- knowledge-model-wrong (Stage 1 or Stage 2): always PIPELINE ---
    if ftype == "knowledge-model-wrong":
        correct = finding.get("correct_value", "")
        if correct:
            evidence = (
                f"Stage 1: profile package_name '{old_value}' does not match "
                f"build file value '{correct}' in clone cache. Update profile YAML."
            )
        else:
            evidence = (
                f"Stage 2: api_surface entry '{old_value}' not found in clone cache source. "
                f"May be phantom API or renamed class. Re-run S-34 (repo-scout)."
            )
        return {
            "origin_class": PIPELINE,
            "origin_subclass": SUB_PROFILE_STALE if correct else SUB_EXTRACTION_MISS,
            "origin_certainty": HIGH,
            "origin_evidence": evidence,
            "repair_route": ROUTE_HUMAN,
            "tier3_non_determinism_flag": False,
        }

    # --- phantom-api: always PIPELINE (extraction problem) ---
    if ftype == "phantom-api":
        return {
            "origin_class": PIPELINE,
            "origin_subclass": SUB_EXTRACTION_MISS,
            "origin_certainty": HIGH,
            "origin_evidence": (
                f"api_surface.json lists '{old_value}' but it was not found in "
                f"clone cache source (Stage 2 grep). Re-run S-34 (repo-scout)."
            ),
            "repair_route": ROUTE_HUMAN,
            "tier3_non_determinism_flag": False,
        }

    # --- wrong-package: depends on whether generator or profile is at fault ---
    if ftype == "wrong-package":
        correct = finding.get("correct_value", "")
        if old_value and correct and old_value != correct:
            # Stage 1 already corrected the profile in-memory — finding means
            # content uses the old (wrong) package name. This is a CONTENT fix.
            return {
                "origin_class": CONTENT,
                "origin_subclass": SUB_HALLUCINATION,
                "origin_certainty": HIGH,
                "origin_evidence": (
                    f"Content declares package '{old_value}'; correct value is '{correct}'. "
                    f"Generator used the wrong package name. Wave 1 auto-fix via S-46."
                ),
                "repair_route": ROUTE_S46,
                "tier3_non_determinism_flag": False,
            }
        # No correct_value: package in content doesn't match profile — unclear which is wrong
        return {
            "origin_class": AMBIGUOUS,
            "origin_subclass": SUB_PROFILE_STALE,
            "origin_certainty": MEDIUM,
            "origin_evidence": (
                f"Package '{old_value}' does not match known package. "
                f"Could be stale profile or generator using wrong package. "
                f"Verify profile discovered_actuals.package_name against build file."
            ),
            "repair_route": ROUTE_AMBIGUOUS,
            "tier3_non_determinism_flag": False,
        }

    # --- wrong-api-name: disambiguation required ---
    if ftype == "wrong-api-name":
        # If token IS in api_surface.json despite the finding, this is a usage context
        # issue (wrong method call pattern, deprecated usage) — CONTENT, not extraction miss.
        if old_value and old_value in api_names:
            return {
                "origin_class": CONTENT,
                "origin_subclass": SUB_HALLUCINATION,
                "origin_certainty": MEDIUM,
                "origin_evidence": (
                    f"Token '{old_value}' exists in api_surface.json but was flagged "
                    f"by Tier {tier} as wrong usage/context. Likely a prose accuracy issue. "
                    f"S-26 can improve the surrounding content."
                ),
                "repair_route": ROUTE_S26,
                "tier3_non_determinism_flag": False,
            }

        # Token not in api_surface — check whether it exists in clone cache source.
        if no_grep:
            return {
                "origin_class": AMBIGUOUS,
                "origin_subclass": SUB_EXTRACTION_MISS,
                "origin_certainty": LOW,
                "origin_evidence": (
                    f"Token '{old_value}' not in api_surface.json. "
                    f"Clone cache grep skipped (--no-grep). "
                    f"Cannot distinguish extraction miss from generator hallucination."
                ),
                "repair_route": ROUTE_AMBIGUOUS,
                "tier3_non_determinism_flag": False,
            }

        grep_result = _grep_clone_cache(old_value, clone_cache_path)
        if grep_result == "found":
            return {
                "origin_class": PIPELINE,
                "origin_subclass": SUB_EXTRACTION_MISS,
                "origin_certainty": HIGH,
                "origin_evidence": (
                    f"Token '{old_value}' found in clone cache source but absent from "
                    f"api_surface.json. Scout missed this API during extraction. "
                    f"Re-run S-34 (repo-scout) for {family}/{platform}."
                ),
                "repair_route": ROUTE_HUMAN,
                "tier3_non_determinism_flag": False,
            }
        elif grep_result == "not-found":
            return {
                "origin_class": CONTENT,
                "origin_subclass": SUB_HALLUCINATION,
                "origin_certainty": HIGH,
                "origin_evidence": (
                    f"Token '{old_value}' not in api_surface.json AND not found in "
                    f"clone cache source. Generator hallucinated this API. "
                    f"S-46 wave 2 LLM substitution can replace it."
                ),
                "repair_route": ROUTE_S46,
                "tier3_non_determinism_flag": False,
            }
        else:
            return {
                "origin_class": AMBIGUOUS,
                "origin_subclass": SUB_EXTRACTION_MISS,
                "origin_certainty": LOW,
                "origin_evidence": (
                    f"Token '{old_value}' not in api_surface.json. "
                    f"Clone cache grep failed or timed out. "
                    f"Cannot distinguish extraction miss from hallucination."
                ),
                "repair_route": ROUTE_AMBIGUOUS,
                "tier3_non_determinism_flag": False,
            }

    # --- wrong-claim: Tier 3 LLM finding, disambiguation via claims.json ---
    if ftype == "wrong-claim":
        # If llm_confidence is too low, treat as ambiguous regardless
        if llm_conf is not None and llm_conf < _LLM_MIN_CONFIDENCE:
            return {
                "origin_class": AMBIGUOUS,
                "origin_subclass": SUB_LOW_CONFIDENCE,
                "origin_certainty": LOW,
                "origin_evidence": (
                    f"LLM confidence {llm_conf:.2f} < {_LLM_MIN_CONFIDENCE} threshold. "
                    f"Finding may be unreliable. Requires human review."
                ),
                "repair_route": ROUTE_AMBIGUOUS,
                "tier3_non_determinism_flag": False,
            }
        matched_claim = _find_claim_in_claims(old_value, claims)
        if matched_claim:
            conf = matched_claim.get("confidence", matched_claim.get("enricher_confidence", 1.0))
            if isinstance(conf, (int, float)):
                if conf >= _ENRICHMENT_HIGH_CONFIDENCE:
                    return {
                        "origin_class": PIPELINE,
                        "origin_subclass": SUB_ENRICHMENT_ERROR,
                        "origin_certainty": MEDIUM,
                        "origin_evidence": (
                            f"Claim '{old_value[:60]}' found in claims.json with confidence {conf:.2f}. "
                            f"Enrichment produced this claim confidently but LLM found it inaccurate. "
                            f"Enrichment logic may have captured a wrong value. Re-run S-37."
                        ),
                        "repair_route": ROUTE_HUMAN,
                        "tier3_non_determinism_flag": False,
                    }
                elif conf < _ENRICHMENT_LOW_CONFIDENCE:
                    return {
                        "origin_class": PIPELINE,
                        "origin_subclass": SUB_LOW_CONFIDENCE,
                        "origin_certainty": MEDIUM,
                        "origin_evidence": (
                            f"Claim '{old_value[:60]}' found in claims.json with low confidence {conf:.2f}. "
                            f"Low-confidence claims should not have reached generated content. "
                            f"Check enrichment threshold configuration."
                        ),
                        "repair_route": ROUTE_HUMAN,
                        "tier3_non_determinism_flag": False,
                    }
            # Claim found but confidence unclear → PIPELINE/enrichment-error
            return {
                "origin_class": PIPELINE,
                "origin_subclass": SUB_ENRICHMENT_ERROR,
                "origin_certainty": LOW,
                "origin_evidence": (
                    f"Claim '{old_value[:60]}' found in claims.json (confidence unknown). "
                    f"LLM found the claim inaccurate. Review enrichment output."
                ),
                "repair_route": ROUTE_HUMAN,
                "tier3_non_determinism_flag": False,
            }
        # Claim not in claims.json at all → generator fabricated it
        return {
            "origin_class": CONTENT,
            "origin_subclass": SUB_HALLUCINATION,
            "origin_certainty": MEDIUM,
            "origin_evidence": (
                f"Claim '{old_value[:60]}' not found in claims.json. "
                f"Generator fabricated this claim without knowledge backing. "
                f"S-26 heal-page can improve the content."
            ),
            "repair_route": ROUTE_S26,
            "tier3_non_determinism_flag": False,
        }

    # --- unimplemented-as-working: check limitations.md ---
    if ftype == "unimplemented-as-working":
        if _token_in_limitations(old_value, family, platform):
            return {
                "origin_class": CONTENT,
                "origin_subclass": SUB_HALLUCINATION,
                "origin_certainty": MEDIUM,
                "origin_evidence": (
                    f"'{old_value}' appears in limitations.md but content claims it works. "
                    f"Generator used a claim despite documented limitation. S-26 can fix this."
                ),
                "repair_route": ROUTE_S26,
                "tier3_non_determinism_flag": False,
            }
        return {
            "origin_class": PIPELINE,
            "origin_subclass": SUB_ENRICHMENT_ERROR,
            "origin_certainty": MEDIUM,
            "origin_evidence": (
                f"'{old_value}' flagged as unimplemented but not found in limitations.md. "
                f"Enrichment did not capture this limitation. Re-run S-37 (knowledge-enrich)."
            ),
            "repair_route": ROUTE_HUMAN,
            "tier3_non_determinism_flag": False,
        }

    # --- missing-section / missing-page: check site_plan ---
    if ftype in ("missing-section", "missing-page"):
        page_path = finding.get("file", "")
        in_plan = _page_in_site_plan(family, platform, page_path)
        if in_plan is True:
            return {
                "origin_class": CONTENT,
                "origin_subclass": SUB_PLANNER_GAP,
                "origin_certainty": MEDIUM,
                "origin_evidence": (
                    f"Page '{page_path}' is in site_plan.yaml but does not exist. "
                    f"Generation was planned but never ran or was skipped. "
                    f"S-26 or S-19 can generate it."
                ),
                "repair_route": ROUTE_S26,
                "tier3_non_determinism_flag": False,
            }
        elif in_plan is False:
            return {
                "origin_class": PIPELINE,
                "origin_subclass": SUB_PLANNER_GAP,
                "origin_certainty": MEDIUM,
                "origin_evidence": (
                    f"Page '{page_path}' missing AND not in site_plan.yaml. "
                    f"Planner never scheduled this page. "
                    f"Re-run S-47 or S-82 (site-plan / delta-site-plan)."
                ),
                "repair_route": ROUTE_HUMAN,
                "tier3_non_determinism_flag": False,
            }
        # No site plan at all — section-level detection
        return {
            "origin_class": PIPELINE,
            "origin_subclass": SUB_PLANNER_GAP,
            "origin_certainty": LOW,
            "origin_evidence": (
                f"Mandatory section '{page_path}' has no content files. "
                f"No site_plan.yaml found — cannot confirm whether planner or generator failed. "
                f"Run S-47 (site-plan) to generate a plan, then re-evaluate."
            ),
            "repair_route": ROUTE_HUMAN,
            "tier3_non_determinism_flag": False,
        }

    # --- structural-reference-page: check api_surface for the class ---
    if ftype == "structural-reference-page":
        if old_value and api_names and old_value in api_names:
            return {
                "origin_class": CONTENT,
                "origin_subclass": SUB_HALLUCINATION,
                "origin_certainty": MEDIUM,
                "origin_evidence": (
                    f"Class '{old_value}' is in api_surface.json but reference page is "
                    f"structurally malformed. Generator produced an invalid page. "
                    f"S-26 can repair the page structure."
                ),
                "repair_route": ROUTE_S26,
                "tier3_non_determinism_flag": False,
            }
        return {
            "origin_class": PIPELINE,
            "origin_subclass": SUB_EXTRACTION_MISS,
            "origin_certainty": MEDIUM,
            "origin_evidence": (
                f"Class '{old_value}' not found in api_surface.json. "
                f"Scout may have missed this class. Re-run S-34 (repo-scout)."
            ),
            "repair_route": ROUTE_HUMAN,
            "tier3_non_determinism_flag": False,
        }

    # --- needs-review (LLM unavailable) ---
    if ftype == "needs-review":
        return {
            "origin_class": AMBIGUOUS,
            "origin_subclass": SUB_LOW_CONFIDENCE,
            "origin_certainty": LOW,
            "origin_evidence": (
                "LLM was unavailable during evaluation. "
                "Cannot classify without LLM verification. "
                "Re-run with LLM available."
            ),
            "repair_route": ROUTE_AMBIGUOUS,
            "tier3_non_determinism_flag": False,
        }

    # --- Unknown finding type ---
    return {
        "origin_class": AMBIGUOUS,
        "origin_subclass": SUB_LOW_CONFIDENCE,
        "origin_certainty": LOW,
        "origin_evidence": f"Unknown finding type '{ftype}'. Cannot classify automatically.",
        "repair_route": ROUTE_AMBIGUOUS,
        "tier3_non_determinism_flag": is_non_det,
    }


# ---------------------------------------------------------------------------
# Main annotator
# ---------------------------------------------------------------------------

def annotate_findings(
    findings: list[dict],
    family: str,
    platform: str,
    api_surface_path: Path,
    claims_path: Path,
    clone_cache_path: Path,
    *,
    no_grep: bool = False,
) -> list[dict]:
    """Annotate all findings with origin classification fields.

    Returns a new list; input findings are not mutated.
    """
    api_data = _load_api_surface(api_surface_path)
    api_names = _build_api_name_set(api_data)
    claims = _load_claims(claims_path)

    annotated: list[dict] = []
    for finding in findings:
        annotation = classify_finding(
            finding, family, platform, api_names, claims, clone_cache_path,
            no_grep=no_grep,
        )
        annotated_finding = dict(finding)  # shallow copy; don't mutate original
        annotated_finding.update(annotation)
        annotated.append(annotated_finding)
        log.debug(
            "  %s → %s/%s [%s] route=%s non_det=%s",
            finding.get("id", "?"),
            annotation["origin_class"],
            annotation["origin_subclass"],
            annotation["origin_certainty"],
            annotation["repair_route"],
            annotation["tier3_non_determinism_flag"],
        )

    return annotated


def build_summary(annotated: list[dict]) -> dict:
    """Build a summary of origin classifications."""
    by_class: dict[str, int] = {}
    by_route: dict[str, int] = {}
    non_det_count = 0
    for f in annotated:
        cls = f.get("origin_class", AMBIGUOUS)
        route = f.get("repair_route", ROUTE_AMBIGUOUS)
        by_class[cls] = by_class.get(cls, 0) + 1
        by_route[route] = by_route.get(route, 0) + 1
        if f.get("tier3_non_determinism_flag"):
            non_det_count += 1
    return {
        "total": len(annotated),
        "by_class": by_class,
        "by_route": by_route,
        "tier3_non_deterministic_count": non_det_count,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Annotate gap-eval findings with pipeline origin classification."
    )
    parser.add_argument("gap_eval_json", help="Path to gap-eval JSON output file")
    parser.add_argument("family", help="Product family (e.g. 3d)")
    parser.add_argument("platform", help="Platform (e.g. java)")
    parser.add_argument("--api-surface", type=Path, default=None,
                        help="Override path to api_surface.json")
    parser.add_argument("--claims", type=Path, default=None,
                        help="Override path to claims.json")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output JSON path (default: {input}-origin.json)")
    parser.add_argument("--no-grep", action="store_true",
                        help="Skip clone-cache grep; classify wrong-api-name as AMBIGUOUS")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print classifications without writing output")
    args = parser.parse_args()

    # Load input
    input_path = Path(args.gap_eval_json)
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Cannot parse input JSON: %s", exc)
        sys.exit(1)

    findings = data.get("findings", [])
    family = args.family
    platform = args.platform

    api_surface_path = args.api_surface or _default_api_surface_path(family, platform)
    claims_path = args.claims or _default_claims_path(family, platform)
    clone_cache_path = _default_clone_cache_path(family, platform)

    log.info(
        "Classifying %d findings for %s/%s (no_grep=%s)",
        len(findings), family, platform, args.no_grep,
    )

    annotated = annotate_findings(
        findings, family, platform, api_surface_path, claims_path, clone_cache_path,
        no_grep=args.no_grep,
    )
    summary = build_summary(annotated)

    # Print summary regardless of dry-run
    log.info("Classification summary: %s", summary)
    for cls, count in summary.get("by_class", {}).items():
        log.info("  %s: %d", cls, count)
    for route, count in summary.get("by_route", {}).items():
        log.info("  Route %s: %d", route, count)
    if summary.get("tier3_non_deterministic_count"):
        log.warning(
            "%d Tier 3 non-deterministic findings routed to AMBIGUOUS "
            "(will stabilise after second run with tier3_cache active)",
            summary["tier3_non_deterministic_count"],
        )

    if args.dry_run:
        log.info("Dry run — no output written.")
        return

    # Determine output path
    out_path = args.out or input_path.with_name(input_path.stem + "-origin.json")
    output = dict(data)  # preserve all original fields
    output["findings"] = annotated
    output["origin_summary"] = summary

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    log.info("Annotated findings written to %s", out_path)


if __name__ == "__main__":
    main()
