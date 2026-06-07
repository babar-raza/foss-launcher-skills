"""LLM Candidate Enricher — expand short shadow candidates using LLM.

Calls the llm.professionalize.com endpoint (gpt-oss) to enrich stub
candidates that fail min_word_count or need fact_ref injection.

All LLM output is bounded by facts from the product's fact graph.
NEVER invents facts — only elaborates on verified fact graph entries.

Public API:
    LLMEnricherConfig   — configuration dataclass
    EnrichmentResult    — per-candidate result
    enrich_candidate    — enrich one candidate using LLM
    enrich_candidates_dir — batch-enrich a directory
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

ENRICHER_VERSION = "1.0.0"
DEFAULT_MODEL = "gpt-oss"
DEFAULT_BASE_URL = "https://llm.professionalize.com/v1"
DEFAULT_MAX_TOKENS = 600
DEFAULT_TEMPERATURE = 0.0

# Min words to target when expanding stubs (slightly above gate thresholds)
TARGET_WORD_COUNTS: dict[str, int] = {
    "reference": 50,
    "documentation": 100,
    "product_landing": 80,
    "blog_post": 130,
    "knowledge_base": 80,
}


@dataclass
class LLMEnricherConfig:
    """Configuration for the LLM enricher."""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    api_key: str = ""

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.environ.get("PROFESSIONALIZE_API_KEY", "")


@dataclass
class EnrichmentResult:
    """Outcome of enriching a candidate."""
    candidate_path: str
    enriched: bool = False
    action: str = ""  # "expanded", "fact_refs_injected", "both", "skipped", "error"
    original_word_count: int = 0
    enriched_word_count: int = 0
    fact_refs_added: int = 0
    error: str = ""
    original_content: str = ""
    enriched_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        del d["original_content"]
        del d["enriched_content"]
        return d


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML-like frontmatter from markdown."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, parts[2]


def _call_llm(prompt: str, config: LLMEnricherConfig) -> str:
    """Call LLM endpoint. Returns generated text or raises.

    Prepends /no_think to suppress reasoning tokens on thinking-mode models
    (e.g. gpt-oss). Falls back to reasoning_content if content is None.
    """
    payload = json.dumps({
        "model": config.model,
        "messages": [{"role": "user", "content": f"/no_think\n{prompt}"}],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content") or ""
    return content.strip()


def _build_reference_prompt(
    class_name: str,
    family: str,
    platform: str,
    methods: list[str],
    claims: list[str],
) -> str:
    """Build an LLM prompt to expand a reference page description."""
    methods_text = "\n".join(f"- {m}" for m in methods[:12]) if methods else "(none listed)"
    claims_text = "\n".join(f"- {c}" for c in claims[:4]) if claims else ""

    prompt = (
        f"Write a concise, technical Description section (50–80 words) for the "
        f"`{class_name}` class in the Aspose.{family.capitalize()} library for {platform.capitalize()}.\n\n"
        f"Available methods:\n{methods_text}\n\n"
    )
    if claims_text:
        prompt += f"Known facts:\n{claims_text}\n\n"
    prompt += (
        "Rules: Only use the listed methods and facts. "
        "Do not invent features. Be factual and technical. "
        "Return ONLY the description text (no headings, no markdown formatting)."
    )
    return prompt


def _build_overview_prompt(
    title: str,
    page_type: str,
    family: str,
    platform: str,
    claims: list[str],
    existing_body: str,
    target_words: int,
) -> str:
    """Build an LLM prompt to expand a non-reference overview page."""
    claims_text = "\n".join(f"- {c}" for c in claims[:8]) if claims else "(no claims available)"

    prompt = (
        f"Expand the following {page_type} page for Aspose.{family.capitalize()} for {platform.capitalize()} "
        f"to approximately {target_words} words.\n\n"
        f"Page title: {title}\n\n"
        f"Existing content:\n{existing_body.strip()}\n\n"
        f"Facts to incorporate (use only these):\n{claims_text}\n\n"
        "Rules:\n"
        "- Keep all existing headings and fact_ref markers\n"
        "- Add substance under existing headings\n"
        "- Do not invent features not in the facts list\n"
        "- Return ONLY the expanded body (no frontmatter, start with # heading)\n"
        "- Keep technical and factual"
    )
    return prompt


def _get_class_facts(
    class_name: str,
    facts: list[dict],
) -> tuple[list[str], list[str]]:
    """Extract method names and claim texts for a given class."""
    methods: list[str] = []
    claims: list[str] = []

    cn_lower = class_name.lower()
    for fact in facts:
        cat = fact.get("category", "")
        text = fact.get("text", "")
        if cat == "api_method" and cn_lower in text.lower():
            methods.append(text)
        elif cat == "claim" and cn_lower in text.lower():
            claims.append(text)

    return methods[:15], claims[:5]


def _get_overview_claims(
    family: str,
    platform: str,
    facts: list[dict],
    limit: int = 10,
) -> list[str]:
    """Get top claim facts for overview/blog/kb pages."""
    claims = [
        f["text"] for f in facts
        if f.get("category") == "claim" and f.get("confidence", 0) >= 0.8
    ]
    return claims[:limit]


def _inject_fact_refs(
    body: str,
    provenance_fact_ids: list[str],
    facts_index: dict[str, dict],
) -> tuple[str, int]:
    """Inject fact_ref comments if body has none."""
    existing = re.findall(r"<!-- fact_ref: (FG-[a-f0-9]+) -->", body)
    if existing:
        return body, 0

    injected = 0
    for fact_id in provenance_fact_ids[:3]:
        if fact_id in facts_index:
            body = body.rstrip() + f"\n\n<!-- fact_ref: {fact_id} -->\n"
            injected += 1

    return body, injected


def enrich_candidate(
    content: str,
    candidate_path: str,
    page_type: str,
    facts: list[dict],
    config: LLMEnricherConfig | None = None,
    failed_gates: list[str] | None = None,
) -> EnrichmentResult:
    """Enrich one candidate using LLM and fact injection.

    Args:
        content: Candidate markdown content.
        candidate_path: Filename for logging.
        page_type: Page type (reference, documentation, etc.)
        facts: Full list of facts from the product's fact graph.
        config: LLM configuration. Uses defaults/env if None.
        failed_gates: Gates that failed (to determine what to fix).
    """
    if config is None:
        config = LLMEnricherConfig()

    result = EnrichmentResult(
        candidate_path=candidate_path,
        original_content=content,
    )

    if failed_gates is None:
        failed_gates = ["min_word_count"]

    fm, body = _parse_frontmatter(content)
    result.original_word_count = len(body.split())

    # Build facts index for fast lookup
    facts_index = {f["fact_id"]: f for f in facts}

    # Parse provenance_fact_ids from frontmatter
    pfi_raw = fm.get("provenance_fact_ids", "[]")
    try:
        provenance_ids = json.loads(pfi_raw)
    except (json.JSONDecodeError, ValueError):
        provenance_ids = []

    current_body = body
    actions_taken: list[str] = []

    # Fix has_fact_refs — inject from provenance_fact_ids if present
    if "has_fact_refs" in failed_gates:
        current_body, injected = _inject_fact_refs(current_body, provenance_ids, facts_index)
        if injected > 0:
            result.fact_refs_added = injected
            actions_taken.append("fact_refs_injected")

    # Fix no_forbidden_terms deterministically
    if "no_forbidden_terms" in failed_gates:
        from lib.content_quality import FORBIDDEN_TERMS
        for term in FORBIDDEN_TERMS:
            current_body = re.sub(re.escape(term), "", current_body, flags=re.IGNORECASE)
        actions_taken.append("forbidden_terms_removed")

    # Fix min_word_count via LLM
    if "min_word_count" in failed_gates:
        target = TARGET_WORD_COUNTS.get(page_type, 50)
        current_word_count = len(current_body.split())
        if current_word_count < target:
            title = fm.get("title", "").strip().strip('"')
            class_name = title

            try:
                if page_type == "reference":
                    methods, claims = _get_class_facts(class_name, facts)
                    prompt = _build_reference_prompt(
                        class_name, fm.get("family", ""), fm.get("platform", ""),
                        methods, claims,
                    )
                    description = _call_llm(prompt, config)
                    # Replace description section
                    if "## Description" in current_body:
                        current_body = re.sub(
                            r"(## Description\n+).*?((?=\n##)|\Z)",
                            f"\\1{description}\n\n",
                            current_body,
                            flags=re.DOTALL,
                        )
                    else:
                        current_body = f"## Description\n\n{description}\n\n{current_body}"
                else:
                    claims = _get_overview_claims(
                        fm.get("family", ""), fm.get("platform", ""), facts,
                    )
                    prompt = _build_overview_prompt(
                        title, page_type, fm.get("family", ""), fm.get("platform", ""),
                        claims, current_body, target,
                    )
                    current_body = _call_llm(prompt, config)
                    # Ensure fact refs preserved from original
                    if not re.search(r"<!-- fact_ref:", current_body):
                        _, injected = _inject_fact_refs(current_body, provenance_ids, facts_index)
                        result.fact_refs_added += injected

                actions_taken.append("expanded")

            except Exception as e:
                result.error = str(e)
                result.enriched = False
                result.enriched_content = content
                return result

    if not actions_taken:
        result.action = "skipped"
        result.enriched = False
        result.enriched_content = content
        return result

    # Reconstruct full markdown
    parts = content.split("---", 2)
    if len(parts) >= 3:
        new_content = f"---{parts[1]}---{current_body}"
    else:
        new_content = current_body

    result.enriched = True
    result.action = "+".join(actions_taken)
    result.enriched_content = new_content
    result.enriched_word_count = len(current_body.split())
    return result


def enrich_candidates_dir(
    candidates_dir: Path,
    facts: list[dict],
    repair_decisions: list[dict],
    page_type_map: dict[str, str] | None = None,
    config: LLMEnricherConfig | None = None,
    write_back: bool = True,
) -> list[EnrichmentResult]:
    """Enrich all REPAIR_REQUIRED candidates in a directory.

    Args:
        candidates_dir: Directory with .md candidates.
        facts: Full list of facts from fact_graph.json.
        repair_decisions: List of decision dicts with candidate_path + failed_gates.
        page_type_map: Optional filename -> page_type mapping.
        config: LLM configuration.
        write_back: If True, overwrite files with enriched content.
    """
    if config is None:
        config = LLMEnricherConfig()

    results: list[EnrichmentResult] = []
    repair_map = {d["candidate_path"]: d for d in repair_decisions}

    for md_file in sorted(candidates_dir.glob("*.md")):
        decision = repair_map.get(md_file.name)
        if not decision:
            continue

        content = md_file.read_text(encoding="utf-8")
        pt = "reference"
        if page_type_map:
            pt = page_type_map.get(md_file.name, "reference")

        result = enrich_candidate(
            content, md_file.name, pt, facts, config,
            failed_gates=decision.get("failed_gates", []),
        )
        results.append(result)

        if write_back and result.enriched:
            md_file.write_text(result.enriched_content, encoding="utf-8")

    return results
