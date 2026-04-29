#!/usr/bin/env python3
"""Dual-tier embedding helper for knowledge artifacts.

Embeds knowledge artifacts from knowledge/{family}/{platform}/merged/
into vector stores at knowledge/_vectors/.

Usage:
    python scripts/pipeline/embed.py {family} {platform}
    python scripts/pipeline/embed.py all

    # Gap-eval mode: per-product API surface index for S-43 Tier 2 vector search
    python scripts/pipeline/embed.py gap-index {family} {platform}
    python scripts/pipeline/embed.py gap-index all

    # Synthesis mode: embed all findings for S-45 cross-product clustering
    python scripts/pipeline/embed.py findings-index
"""

import argparse
import json
import logging
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopwords for TF-IDF fallback
# ---------------------------------------------------------------------------
STOPWORDS = frozenset(
    "a about above after again against all am an and any are aren't as at be "
    "because been before being below between both but by can could couldn't did "
    "didn't do does doesn't doing don't down during each few for from further "
    "get got had has have having he her here hers herself him himself his how "
    "however i if in into is isn't it its itself just let like ll me might more "
    "most mustn't my myself no nor not now of off on once only or other our ours "
    "ourselves out over own re s same shall she should shouldn't so some such "
    "than that the their theirs them themselves then there these they this those "
    "through to too under until up us ve very was wasn't we were weren't what "
    "when where which while who whom why will with won't would wouldn't you "
    "your yours yourself yourselves".split()
)

# ---------------------------------------------------------------------------
# TF-IDF fallback
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """Lowercase words, remove stopwords and tokens with length <= 2."""
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def compute_tf(tokens: list[str]) -> dict[str, float]:
    """Term frequency: count / total."""
    counts = Counter(tokens)
    total = len(tokens) or 1
    return {t: c / total for t, c in counts.items()}


def compute_idf(documents: list[list[str]]) -> dict[str, float]:
    """Inverse document frequency with smoothing: log(1 + N/df)."""
    n = len(documents)
    df: dict[str, int] = {}
    for doc in documents:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    return {term: math.log(1 + n / count) for term, count in df.items()}


def compute_tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    """Sparse TF-IDF vector."""
    tf = compute_tf(tokens)
    return {t: tf[t] * idf.get(t, 0.0) for t in tf}


def cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    keys = set(vec1) & set(vec2)
    if not keys:
        return 0.0
    dot = sum(vec1[k] * vec2[k] for k in keys)
    mag1 = math.sqrt(sum(v * v for v in vec1.values()))
    mag2 = math.sqrt(sum(v * v for v in vec2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


# ---------------------------------------------------------------------------
# EmbeddingClient — OpenAI-compatible /v1/embeddings
# ---------------------------------------------------------------------------

class EmbeddingClient:
    """Client for OpenAI-compatible /v1/embeddings endpoint."""

    def __init__(self, endpoint: str, model: str, api_key: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key

    def is_available(self) -> bool:
        """Probe endpoint with trivial request."""
        if requests is None:
            log.debug("requests library not installed — API embedding unavailable")
            return False
        try:
            resp = requests.post(
                self.endpoint,
                json={"model": self.model, "input": ["probe"]},
                headers=self._headers(),
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as exc:
            log.warning("Embedding endpoint probe failed (%s): %s", self.endpoint, exc)
            return False

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Batch embed texts. Splits into chunks of batch_size."""
        if requests is None:
            raise RuntimeError("requests library required for API embeddings: pip install requests")
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = requests.post(
                self.endpoint,
                json={"model": self.model, "input": batch},
                headers=self._headers(),
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Embedding API returned {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
            for item in items:
                all_vectors.append(item["embedding"])
        return all_vectors

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

VECTORS_DIR = Path("knowledge/_vectors")
DEFAULT_CONFIG_PATH = VECTORS_DIR / "config.json"

DEFAULT_CONFIG = {
    "tiers": [
        {
            "id": "api",
            "provider": "professionalize",
            "endpoint": "https://llm.professionalize.com/v1/embeddings",
            "model": "qwen3-embedding-8b",
            "api_key_env": "PROFESSIONALIZE_API_KEY",
            "dimensions": None,
            "last_embedded": None,
        },
        {
            "id": "local",
            "provider": "ollama",
            "endpoint": "http://localhost:11434/v1/embeddings",
            "model": "nomic-embed-text",
            "api_key_env": None,
            "dimensions": 768,
            "last_embedded": None,
        },
    ],
    "active_tier": "api",
    "claim_count": 0,
    "content_chunk_count": 0,
}


def load_or_create_config(config_path: Path | None = None) -> dict:
    """Load config.json or create from defaults."""
    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy


def save_config(config: dict, config_path: Path | None = None) -> None:
    """Persist config.json atomically (write to .tmp, then rename)."""
    # lazy-import guard: core.fs is a sibling module; deferred to avoid circular imports.
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> pipeline/
    from core.fs import atomic_write

    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(config, indent=2))
    log.info("Config saved to %s", path)


# ---------------------------------------------------------------------------
# Content chunking
# ---------------------------------------------------------------------------

def chunk_content_pages(family: str, platform: str) -> dict[str, str]:
    """Read content pages and split into chunks keyed by file:index."""
    from content_discovery import SITE_PATHS  # noqa: PLC0415
    chunks: dict[str, str] = {}
    content_dirs = [
        Path(pattern.format(family=family, platform=platform))
        for _, pattern in SITE_PATHS
    ]
    for content_dir in content_dirs:
        if not content_dir.exists():
            continue
        md_files = sorted(content_dir.rglob("*.md"))[:100]
        for md_file in md_files:
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                log.warning("Cannot read %s: %s", md_file, exc)
                continue
            paragraphs = text.split("\n\n")
            for i, para in enumerate(paragraphs):
                para = para.strip()
                if len(para) < 50:
                    continue
                if para.startswith("---"):
                    continue
                key = f"{md_file}:{i}"
                chunks[key] = para
    return chunks


# ---------------------------------------------------------------------------
# Embed & save
# ---------------------------------------------------------------------------

def embed_and_save(
    client: EmbeddingClient,
    texts: dict[str, str],
    output_path: Path,
    *,
    expected_dimensions: int | None = None,
    provider: str | None = None,
) -> None:
    """Embed texts and save to JSON.

    Args:
        expected_dimensions: If provided, validate that every vector has this
            many dimensions. Raises ValueError on mismatch (fail-fast before write).
        provider: Provider name to record in the output metadata.
    """
    keys = sorted(texts.keys())
    text_list = [texts[k] for k in keys]
    vectors = client.embed_batch(text_list)

    # Dimension validation gate — fail before writing corrupt data to disk.
    if expected_dimensions is not None and vectors:
        actual = len(vectors[0])
        if actual != expected_dimensions:
            raise ValueError(
                f"Dimension mismatch: expected {expected_dimensions}, "
                f"got {actual} from model {client.model}. "
                f"Refusing to write {output_path}."
            )

    actual_dims = len(vectors[0]) if vectors else 0
    data = {
        "version": "1.0.0",
        "model": client.model,
        "dimensions": actual_dims,
        "provider": provider or "",
        "count": len(keys),
        "vectors": {k: v for k, v in zip(keys, vectors)},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    log.info("  Saved %d vectors (%d-dim) to %s", len(keys), actual_dims, output_path)


# ---------------------------------------------------------------------------
# Main embedding logic
# ---------------------------------------------------------------------------

def embed_knowledge(
    family: str,
    platform: str,
    config_path: Path | None = None,
    tier_filter: str | None = None,
    knowledge_root: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Embed knowledge artifacts into dual vector stores."""
    _kr = knowledge_root or Path("knowledge")
    merged_dir = _kr / family / platform / "merged"
    if not merged_dir.exists():
        log.warning("No merged knowledge at %s", merged_dir)
        return

    # 1. Load claims
    claims_path = merged_dir / "claims.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8")) if claims_path.exists() else []
    claim_texts = {c["claim_id"]: f"{c['kind']}: {c['text']}" for c in claims}

    # 2. Load API surface
    api_path = merged_dir / "api_surface.json"
    api_data = json.loads(api_path.read_text(encoding="utf-8")) if api_path.exists() else []
    api_texts: dict[str, str] = {}
    for cls in api_data:
        name = cls.get("name", "")
        methods = ", ".join(m.get("name", "") for m in cls.get("method_details", []))
        props = ", ".join(p.get("name", "") for p in cls.get("property_details", []))
        doc = cls.get("docstring", "")
        api_texts[name] = (
            f"class {name}: methods=[{methods}], properties=[{props}], doc={doc}"
        )

    # 3. Load content chunks
    content_texts = chunk_content_pages(family, platform)

    if not claim_texts and not api_texts and not content_texts:
        log.warning("No texts to embed for %s/%s", family, platform)
        return

    log.info(
        "Artifacts: %d claims, %d API entries, %d content chunks",
        len(claim_texts),
        len(api_texts),
        len(content_texts),
    )

    # 4. Dry-run: report what would be embedded, then return
    if dry_run:
        log.info("(dry-run) Would embed %d claims, %d API entries, %d content chunks for %s/%s",
                 len(claim_texts), len(api_texts), len(content_texts), family, platform)
        return

    # 5. Load or create config
    config = load_or_create_config(config_path)

    # 5. Embed into each available tier.
    # Track results per tier: None = skipped/unavailable, True = success, False = failed.
    tier_results: dict[str, bool | None] = {}

    for tier in config["tiers"]:
        if tier_filter and tier["id"] != tier_filter:
            continue

        api_key = ""
        if tier.get("api_key_env"):
            api_key = os.environ.get(tier["api_key_env"], "")

        client = EmbeddingClient(tier["endpoint"], tier["model"], api_key)

        if not client.is_available():
            log.info("Tier '%s' (%s) unavailable, skipping", tier["id"], tier["provider"])
            tier_results[tier["id"]] = None  # skipped — not a failure
            continue

        log.info(
            "Embedding via Tier '%s' (%s, model=%s)",
            tier["id"],
            tier["provider"],
            tier["model"],
        )

        vectors_dir = (_kr / "_vectors") if knowledge_root else VECTORS_DIR
        tier_dir = vectors_dir / tier["id"]
        tier_dir.mkdir(parents=True, exist_ok=True)

        exp_dims = tier.get("dimensions")
        prov_name = tier.get("provider", "")

        try:
            if claim_texts:
                embed_and_save(client, claim_texts, tier_dir / "claims.vectors.json",
                               expected_dimensions=exp_dims, provider=prov_name)
            if api_texts:
                embed_and_save(client, api_texts, tier_dir / "api.vectors.json",
                               expected_dimensions=exp_dims, provider=prov_name)
            if content_texts:
                embed_and_save(client, content_texts, tier_dir / "content.vectors.json",
                               expected_dimensions=exp_dims, provider=prov_name)
            tier_results[tier["id"]] = True
        except Exception as exc:
            log.error("Tier '%s' failed during embedding: %s", tier["id"], exc)
            tier_results[tier["id"]] = False

    attempted = {tid for tid, result in tier_results.items() if result is not None}
    failed = {tid for tid, result in tier_results.items() if result is False}

    if not attempted:
        log.warning(
            "No embedding tiers were available. "
            "TF-IDF (Tier 3) is available at runtime via the tfidf_* functions."
        )

    # 6. Update config ONLY when all attempted tiers succeeded.
    # A partial update (some tiers failed) would leave last_embedded timestamps
    # inconsistent with the actual vector files on disk.
    if attempted and not failed:
        now = datetime.utcnow().isoformat() + "Z"
        for tier in config["tiers"]:
            if tier["id"] in attempted:
                tier["last_embedded"] = now
                # Populate dimensions from the tier's EmbeddingClient model if
                # not already set — ensures config.json reflects reality.
                if tier.get("dimensions") is None:
                    # Read back actual dims from any vector file just written.
                    vectors_dir = (_kr / "_vectors") if knowledge_root else VECTORS_DIR
                    sample = vectors_dir / tier["id"] / "claims.vectors.json"
                    if sample.exists():
                        try:
                            vdata = json.loads(sample.read_text(encoding="utf-8"))
                            tier["dimensions"] = vdata.get("dimensions")
                        except Exception:
                            pass
        config["claim_count"] = len(claim_texts)
        config["content_chunk_count"] = len(content_texts)
        save_config(config, config_path)
    elif failed:
        log.warning(
            "Tiers %s failed — config.json NOT updated to preserve consistency. "
            "Re-run after fixing the failed tiers.",
            sorted(failed),
        )


# ---------------------------------------------------------------------------
# Gap-index: per-product API surface vectors for S-43 Tier 2
# ---------------------------------------------------------------------------

def _pick_client(config: dict) -> tuple[EmbeddingClient | None, dict | None]:
    """Return the first available (EmbeddingClient, tier_dict) from config tiers."""
    for tier in config.get("tiers", []):
        api_key = ""
        if tier.get("api_key_env"):
            api_key = os.environ.get(tier["api_key_env"], "")
        client = EmbeddingClient(tier["endpoint"], tier["model"], api_key)
        if client.is_available():
            log.info(
                "Using tier '%s' (%s, model=%s)", tier["id"], tier["provider"], tier["model"]
            )
            return client, tier
    return None, None


def embed_api_index(
    family: str,
    platform: str,
    config_path: Path | None = None,
    knowledge_root: Path | None = None,
) -> Path | None:
    """Build a per-product API surface vector index for S-43 Tier 2.

    Reads ``knowledge/{family}/{platform}/merged/api_surface.json`` and embeds
    each class entry as a searchable text string.  Output is written to
    ``knowledge/_vectors/{family}/{platform}/api.vectors.json``.

    Returns the output path on success, None if no data or no client.
    """
    _kr = knowledge_root or Path("knowledge")
    api_path = _kr / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        log.error("api_surface.json not found at %s", api_path)
        return None

    api_data = json.loads(api_path.read_text(encoding="utf-8"))
    if not api_data:
        log.warning("api_surface.json is empty for %s/%s", family, platform)
        return None

    # Build one text entry per class, including method/property names.
    texts: dict[str, str] = {}
    for cls in api_data:
        name = cls.get("name", "").strip()
        if not name:
            continue
        methods = " ".join(m.get("name", "") for m in cls.get("method_details", []) if m.get("name"))
        props = " ".join(p.get("name", "") for p in cls.get("property_details", []) if p.get("name"))
        doc = (cls.get("docstring") or "").strip()[:200]
        texts[name] = f"class {name} methods: {methods} properties: {props} {doc}".strip()

    log.info(
        "gap-index %s/%s: %d class entries to embed", family, platform, len(texts)
    )

    config = load_or_create_config(config_path)
    client, tier = _pick_client(config)
    if client is None:
        log.warning(
            "No embedding tier available. "
            "Set PROFESSIONALIZE_API_KEY or ensure Ollama is running."
        )
        return None

    vectors_dir = (_kr / "_vectors") if knowledge_root else VECTORS_DIR
    out_path = vectors_dir / family / platform / "api.vectors.json"
    embed_and_save(
        client, texts, out_path,
        expected_dimensions=tier.get("dimensions") if tier else None,
        provider=tier.get("provider", "") if tier else "",
    )
    return out_path


def embed_findings_index(
    config_path: Path | None = None,
    reports_root: Path | None = None,
    knowledge_root: Path | None = None,
) -> Path | None:
    """Embed all gap-eval findings for S-45 cross-product synthesis.

    Reads all ``reports/gap-analysis/{family}-{platform}.json`` files and
    embeds each finding's description.  Output is written to
    ``knowledge/_vectors/_synthesis/findings.vectors.json``.

    Returns the output path on success, None if no findings.
    """
    _rr = reports_root or Path("reports") / "gap-analysis"
    _kr = knowledge_root or Path("knowledge")

    findings_files = sorted(_rr.glob("*.json")) if _rr.exists() else []
    if not findings_files:
        log.error("No gap-analysis JSON files found under %s", _rr)
        return None

    texts: dict[str, str] = {}
    for jf in findings_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Cannot read %s: %s", jf, exc)
            continue
        repo_key = jf.stem  # e.g. "slides-java"
        for finding in data.get("findings", []):
            fid = finding.get("id", "")
            ftype = finding.get("type", "")
            desc = finding.get("description", "")
            severity = finding.get("severity", "")
            if fid and desc:
                texts[f"{repo_key}::{fid}"] = (
                    f"[{repo_key}] {severity} {ftype}: {desc}"
                )

    if not texts:
        log.warning("No findings to embed (all files empty or malformed)")
        return None

    log.info("findings-index: %d total findings to embed", len(texts))

    config = load_or_create_config(config_path)
    client, tier = _pick_client(config)
    if client is None:
        log.warning("No embedding tier available for findings-index.")
        return None

    vectors_dir = (_kr / "_vectors") if knowledge_root else VECTORS_DIR
    out_path = vectors_dir / "_synthesis" / "findings.vectors.json"
    embed_and_save(
        client, texts, out_path,
        expected_dimensions=tier.get("dimensions") if tier else None,
        provider=tier.get("provider", "") if tier else "",
    )
    return out_path


# ---------------------------------------------------------------------------
# Discovery: find all family/platform pairs
# ---------------------------------------------------------------------------

def discover_targets(knowledge_root: Path | None = None) -> list[tuple[str, str]]:
    """Find all family/platform pairs with merged knowledge."""
    _kr = knowledge_root or Path("knowledge")
    targets: list[tuple[str, str]] = []
    if not _kr.exists():
        return targets
    for family_dir in sorted(_kr.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            merged = platform_dir / "merged"
            if merged.exists():
                targets.append((family_dir.name, platform_dir.name))
    return targets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _make_base_parser(add_positional: bool = True) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--knowledge-root", type=Path, default=None)
    if add_positional:
        p.add_argument("--tier", default=None, choices=["api", "local"])
    return p


def main() -> None:
    raw = sys.argv[1:]

    # Dispatch on first positional argument (the subcommand or family).
    subcmd = raw[0].lower() if raw else ""

    # -----------------------------------------------------------------------
    # gap-index {family} {platform} [--config ...] [--knowledge-root ...]
    # gap-index all [--config ...] [--knowledge-root ...]
    # -----------------------------------------------------------------------
    if subcmd == "gap-index":
        p = _make_base_parser(add_positional=False)
        p.add_argument("subcmd")
        p.add_argument("family")
        p.add_argument("platform", nargs="?", default=None)
        args = p.parse_args(raw)
        if args.family.lower() == "all":
            targets = discover_targets(args.knowledge_root)
            if not targets:
                log.error("No knowledge targets discovered")
                sys.exit(1)
            log.info("gap-index: building API surface index for %d targets", len(targets))
            for family, platform in targets:
                log.info("--- gap-index %s/%s ---", family, platform)
                embed_api_index(family, platform, args.config, args.knowledge_root)
        else:
            if not args.platform:
                p.error("gap-index requires: gap-index {family} {platform}  or  gap-index all")
            result = embed_api_index(args.family, args.platform, args.config, args.knowledge_root)
            if result is None:
                sys.exit(1)

    # -----------------------------------------------------------------------
    # findings-index [--config ...] [--knowledge-root ...] [--reports-root ...]
    # -----------------------------------------------------------------------
    elif subcmd == "findings-index":
        p = _make_base_parser(add_positional=False)
        p.add_argument("subcmd")
        p.add_argument("--reports-root", type=Path, default=None)
        args = p.parse_args(raw)
        result = embed_findings_index(args.config, args.reports_root, args.knowledge_root)
        if result is None:
            sys.exit(1)

    # -----------------------------------------------------------------------
    # Standard knowledge embedding: {family} {platform} or all
    # -----------------------------------------------------------------------
    else:
        parser = argparse.ArgumentParser(
            description="Embed knowledge artifacts into dual vector stores."
        )
        parser.add_argument(
            "family",
            help='Product family (e.g. "3d") or "all" for every discovered target.',
        )
        parser.add_argument(
            "platform",
            nargs="?",
            default=None,
            help='Platform (e.g. "python"). Omit when family is "all".',
        )
        parser.add_argument("--config", type=Path, default=None)
        parser.add_argument("--tier", default=None, choices=["api", "local"])
        parser.add_argument("--knowledge-root", type=Path, default=None)
        parser.add_argument("--dry-run", action="store_true", help="Show what would be embedded without writing")
        args = parser.parse_args(raw)

        if args.family.lower() == "all":
            targets = discover_targets(args.knowledge_root)
            if not targets:
                log.error("No knowledge targets discovered under knowledge/")
                sys.exit(1)
            log.info("Discovered %d targets", len(targets))
            for family, platform in targets:
                log.info("--- %s / %s ---", family, platform)
                embed_knowledge(family, platform, args.config, args.tier, args.knowledge_root, args.dry_run)
        else:
            if not args.platform:
                parser.error("platform is required unless family is 'all'")
            embed_knowledge(args.family, args.platform, args.config, args.tier, args.knowledge_root, args.dry_run)

    log.info("Done.")


if __name__ == "__main__":
    main()
