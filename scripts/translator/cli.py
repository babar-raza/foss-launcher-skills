"""
CLI entry point for the aspose.org translation subsystem.

Usage:
  python -m translator preflight [--provider {auto,llm,ollama,m2m}] [--verbose]
  python -m translator page <src_path> --locales fr,de,ar [--provider {auto,llm,ollama,m2m}] [--model MODEL] [--dry-run]
  python -m translator batch --family slides --platform net [--site docs.aspose.org] [--locales all] [--provider {auto,llm,ollama,m2m}] [--dry-run]
  python -m translator sync [--family FAMILY] [--platform PLATFORM] [--provider {auto,llm,ollama,m2m}]
  python -m translator flush-cache [--lang LANG]
  python -m translator cache-stats

Provider selection:
  --provider auto    (default) Try llm.professionalize.com → Ollama → M2M100
  --provider llm     Force llm.professionalize.com (fail if unavailable)
  --provider ollama  Force local Ollama (fail if unavailable)
  --provider m2m     Force local M2M100 offline backend (fail if not downloaded)
  --offline          Alias for --provider m2m (backward compat)

Thinking-model control:
  TRANSLATE_ALLOW_THINKING_MODELS=1   Allow thinking models when no better option exists
  TRANSLATE_MODEL_BLOCKLIST=pat1,pat2  Additional comma-separated blocklist patterns
"""
from __future__ import annotations
import argparse
import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path

def _load_env() -> None:
    """Load .env from repo root into os.environ (no-op if python-dotenv absent)."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=False)
    except ImportError:
        pass

_load_env()

from translator import ALL_LOCALES, ConfigurationError, BackendUnavailableError
from translator.backends.base import BackendRouter
from translator.cache.sqlite_cache import TranslationCache
from translator.engine.translator import TranslationEngine, ValidationError
from translator.preflight.checker import PreflightChecker, PreflightReport
from translator import provenance_shim as _prov  # foss: standalone provenance shim

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("translator.cli")

_SKILLS_REPO_ROOT = Path(__file__).parent.parent.parent  # foss skills repo root
_CONTENT_REPO_ROOT = Path(  # foss: content lives in external repo
    os.environ.get("CONTENT_REPO_PATH", str(_SKILLS_REPO_ROOT))
)
_REPO_ROOT = _SKILLS_REPO_ROOT  # alias for backward compat
_DEFAULT_CACHE = Path(os.environ["TRANSLATION_CACHE_PATH"]) if "TRANSLATION_CACHE_PATH" in os.environ else _REPO_ROOT / "cache" / "translation_cache.db"
_BUILTIN_DEFAULT_CACHE = _DEFAULT_CACHE  # preserved for configure() reset


def configure(cache_path: "Path | None" = None) -> None:
    """Override _DEFAULT_CACHE for testing. Call with no args to reset to built-in default."""
    global _DEFAULT_CACHE
    _DEFAULT_CACHE = cache_path if cache_path is not None else _BUILTIN_DEFAULT_CACHE


# Known site names and their content root paths
# foss: paths are relative to CONTENT_REPO_PATH/content/
_SITES = {
    "docs.aspose.org": _CONTENT_REPO_ROOT / "content" / "docs.aspose.org",
    "kb.aspose.org": _CONTENT_REPO_ROOT / "content" / "kb.aspose.org",
    "products.aspose.org": _CONTENT_REPO_ROOT / "content" / "products.aspose.org",
    "reference.aspose.org": _CONTENT_REPO_ROOT / "content" / "reference.aspose.org",
    "blog.aspose.org": _CONTENT_REPO_ROOT / "content" / "blog.aspose.org",
}

_ALL_SITES = list(_SITES.keys())


_GRADE_FLOOR = "B"  # Minimum grade required for translation
_PASSING_GRADES = {"A", "B"}


def _read_page_grade(src_path: Path) -> str:
    """Read grade from page frontmatter. Returns grade letter or '' if ungraded."""
    try:
        text = src_path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return ""
    m = re.search(r"^grade:\s*([A-F])\s*$", text, re.MULTILINE)
    return m.group(1) if m else ""


def _check_grade_floor(src_path: Path, skip: bool = False) -> bool:
    """Check if page meets grade floor for translation.

    Returns True if translation should proceed, False if blocked.
    Logs an audit message when --skip-grade-check is used to override.
    """
    grade = _read_page_grade(src_path)
    if not grade:
        # Ungraded pages are allowed (grade may not have been assigned yet)
        return True
    if grade in _PASSING_GRADES:
        return True
    if skip:
        logger.warning(
            "AUDIT: --skip-grade-check override for %s (grade=%s, floor=%s)",
            src_path, grade, _GRADE_FLOOR,
        )
        return True
    logger.error(
        "Grade floor not met: %s has grade %s (minimum: %s). "
        "Use --skip-grade-check to override.",
        src_path, grade, _GRADE_FLOOR,
    )
    return False


def _provider_from_args(args) -> str:
    """Resolve provider from CLI args, respecting --offline backward compat."""
    offline = getattr(args, "offline", False)
    if offline:
        return "m2m"
    provider = getattr(args, "provider", None) or os.environ.get("TRANSLATE_PROVIDER", "auto")
    return provider.strip().lower()


def _run_preflight(provider: str, verbose: bool = False) -> PreflightReport:
    """Run preflight checks and print a summary. Returns the report."""
    checker = PreflightChecker()
    report = checker.run(provider=provider)

    if verbose or report.errors:
        print(report.format_report())
    else:
        print(report.format_summary())

    return report


def _build_engine_from_preflight(
    report: PreflightReport,
    model_override: str | None = None,
    dry_run: bool = False,
) -> TranslationEngine:
    """
    Build a TranslationEngine from a successful PreflightReport.

    model_override: explicit --model flag from CLI (takes precedence over preflight selection)
    dry_run: if True, use in-memory cache
    """
    backends = []

    for backend_name in report.fallback_chain:
        if backend_name == "llm":
            from translator.backends.llm import LLMBackend
            model = model_override or report.selected_model or "recommended"
            backends.append(LLMBackend(model=model))

        elif backend_name == "ollama":
            from translator.backends.ollama import OllamaBackend
            ollama_cap = next(
                (b for b in report.backends if b.name == "ollama"), None
            )
            model = model_override or (ollama_cap.selected_model if ollama_cap else None) or "llama3.2"
            backends.append(OllamaBackend(model=model))

        elif backend_name == "m2m100":
            from translator.backends.m2m import M2MBackend
            backends.append(M2MBackend())

    if not backends:
        logger.error("Preflight succeeded but produced an empty backend list")
        sys.exit(1)

    router = BackendRouter(backends)
    cache = TranslationCache(":memory:") if dry_run else TranslationCache(str(_DEFAULT_CACHE))
    return TranslationEngine(backend=router, cache=cache, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(
        prog="translator",
        description="aspose.org translation subsystem",
    )
    parser.add_argument(
        "--cache-path",
        default=None,
        metavar="FILE",
        help="Override translation cache path (default: cache/translation_cache.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- preflight ---
    p_preflight = sub.add_parser(
        "preflight",
        help="Check available backends and report selection before translating",
    )
    p_preflight.add_argument(
        "--provider", default="auto",
        choices=["auto", "llm", "ollama", "m2m"],
        help="Provider to check (default: auto)",
    )
    p_preflight.add_argument(
        "--verbose", action="store_true",
        help="Print full backend capability report",
    )

    # Shared provider arg (added to each subcommand below)
    def _add_provider_args(p):
        p.add_argument(
            "--provider", default=None,
            choices=["auto", "llm", "ollama", "m2m"],
            help="Translation backend to use (default: auto)",
        )
        p.add_argument(
            "--offline", action="store_true",
            help="Use M2M100 offline backend (alias for --provider m2m)",
        )

    # --- page ---
    p_page = sub.add_parser("page", help="Translate a single file")
    p_page.add_argument("src_path", help="Path to English source .md file")
    p_page.add_argument("--locales", default="all",
                        help="Comma-separated locales (e.g. fr,de,ar) or 'all'")
    p_page.add_argument("--model", help="Override translation model")
    p_page.add_argument("--dry-run", action="store_true",
                        help="Parse and validate but do not write output")
    p_page.add_argument("--skip-grade-check", action="store_true",
                        help="Allow translation of pages below grade floor (audit-logged)")
    _add_provider_args(p_page)

    # --- batch ---
    p_batch = sub.add_parser("batch", help="Translate all files for a family/platform")
    p_batch.add_argument("--family", required=True, help="Product family (e.g. slides)")
    p_batch.add_argument("--platform", required=True, help="Platform (e.g. net)")
    p_batch.add_argument("--site", default="all",
                         help="Site name (e.g. docs.aspose.org) or 'all'")
    p_batch.add_argument("--locales", default="all",
                         help="Comma-separated locales or 'all'")
    p_batch.add_argument("--dry-run", action="store_true")
    p_batch.add_argument("--force", action="store_true",
                         help="Re-translate even if translated file is newer than source")
    p_batch.add_argument("--retry-failed", metavar="MANIFEST",
                         help="Re-run only files with 'failed' status from a prior batch manifest")
    p_batch.add_argument("--skip-grade-check", action="store_true",
                         help="Allow translation of pages below grade floor (audit-logged)")
    _add_provider_args(p_batch)

    # --- sync ---
    p_sync = sub.add_parser("sync", help="Re-translate stale English to locale pairs")
    p_sync.add_argument("--family", help="Filter by family")
    p_sync.add_argument("--platform", help="Filter by platform")
    p_sync.add_argument("--site", default="all")
    p_sync.add_argument("--locales", default="all")
    p_sync.add_argument("--dry-run", action="store_true")
    _add_provider_args(p_sync)

    # --- flush-cache ---
    p_flush = sub.add_parser("flush-cache", help="Remove cached translations")
    p_flush.add_argument("--lang", help="Only flush entries for this language")

    # --- cache-stats ---
    sub.add_parser("cache-stats", help="Print cache statistics")

    # --- audit ---
    p_audit = sub.add_parser("audit", help="Scan existing translations for quality issues")
    p_audit.add_argument("--family", required=True, help="Product family (e.g., cells)")
    p_audit.add_argument("--platform", required=True, help="Platform (e.g., python)")
    p_audit.add_argument("--site", default="all", help="Site to audit (default: all)")
    p_audit.add_argument("--locales", default="all", help="Comma-separated locales or 'all'")
    p_audit.add_argument("--output", default="reports/audit_report.json", help="Output JSON path")
    p_audit.add_argument("--quiet", action="store_true", help="Suppress INFO-level progress output")

    # --- retranslate ---
    p_retranslate = sub.add_parser("retranslate", help="Re-translate files from audit report")
    p_retranslate.add_argument("--report", required=True, help="Path to audit_report.json")
    p_retranslate.add_argument(
        "--severity", default="critical", choices=["critical", "minor", "all"],
        help="Minimum severity to retranslate",
    )
    p_retranslate.add_argument("--dry-run", action="store_true", help="Preview without writing")
    p_retranslate.add_argument("--quiet", action="store_true", help="Suppress INFO-level progress output")
    p_retranslate.add_argument(
        "--max-per-run", type=int, default=100, metavar="N",
        help="Maximum number of files to re-translate per invocation (default: 100)."
    )
    p_retranslate.add_argument(
        "--delay-seconds", type=float, default=0.5, metavar="F",
        help="Seconds to sleep between API calls (default: 0.5). Set to 0 to disable."
    )
    p_retranslate.add_argument("--model", help="Override translation model")
    _add_provider_args(p_retranslate)

    args = parser.parse_args()

    if args.cache_path:
        configure(cache_path=Path(args.cache_path))

    if args.command == "flush-cache":
        _cmd_flush_cache(args)
    elif args.command == "cache-stats":
        _cmd_cache_stats()
    elif args.command == "preflight":
        _cmd_preflight(args)
    elif args.command == "page":
        _cmd_page(args)
    elif args.command == "batch":
        _cmd_batch(args)
    elif args.command == "sync":
        _cmd_sync(args)
    elif args.command == "audit":
        return _cmd_audit(args)
    elif args.command == "retranslate":
        return _cmd_retranslate(args)


def _cmd_preflight(args):
    """Run preflight checks and exit. Exit 0 if a backend is available, 1 otherwise."""
    report = _run_preflight(args.provider, verbose=True)
    if not report.ok():
        sys.exit(1)


def _build_engine(args) -> TranslationEngine:
    """
    Run preflight, print summary, then build and return TranslationEngine.
    Exits with code 1 if preflight fails (no valid backend available).
    """
    provider = _provider_from_args(args)
    dry_run = getattr(args, "dry_run", False)

    # dry_run with no backend configured: skip network checks and use a dummy chain
    if dry_run:
        # Still run preflight to inform the user, but don't fail for dry-run
        report = _run_preflight(provider, verbose=False)
        if not report.ok():
            # For dry-run we warn but don't abort — the engine won't actually call backend
            logger.warning(
                "Preflight failed but --dry-run is set; proceeding without a real backend. "
                "Output will be a parse/validate pass only."
            )
            cache = TranslationCache(":memory:")
            return TranslationEngine(backend=None, cache=cache, dry_run=True)
    else:
        report = _run_preflight(provider, verbose=False)
        if not report.ok():
            sys.exit(1)

    model_override = getattr(args, "model", None)
    return _build_engine_from_preflight(report, model_override=model_override, dry_run=dry_run)


def _parse_locales(locales_str: str) -> list[str]:
    if locales_str.lower() == "all":
        return ALL_LOCALES
    return [lang.strip() for lang in locales_str.split(",") if lang.strip()]


def _write_translation_provenance(
    src_path: Path, tgt_path: Path, subcommand: str
) -> None:
    """Write provenance metadata to a translated output file."""
    try:
        content_root = _CONTENT_REPO_ROOT / "content"  # foss: external content repo
        source_rel = str(src_path.resolve().relative_to(content_root.resolve())).replace("\\", "/")
    except ValueError:
        source_rel = str(src_path).replace("\\", "/")
    _prov.write_provenance(tgt_path, {
        "translation_origin": f"translator-{subcommand}",
        "source_file": source_rel,
        "source_sha": _prov.compute_source_sha(src_path),
        "last_mechanism": "translator",
        "auto_updatable": True,
        "reviewed": False,
    })


def _cmd_page(args):
    engine = _build_engine(args)
    locales = _parse_locales(args.locales)
    src_path = Path(args.src_path)

    if not src_path.exists():
        logger.error(f"Source file not found: {src_path}")
        sys.exit(1)

    skip_grade = getattr(args, "skip_grade_check", False)
    if not _check_grade_floor(src_path, skip=skip_grade):
        sys.exit(1)

    ok_count = fail_count = skip_count = 0

    for lang in locales:
        tgt_path = _derive_output_path(src_path, lang)
        if tgt_path is None:
            logger.warning(f"Cannot derive output path for {src_path} -> {lang}")
            skip_count += 1
            continue

        try:
            summary = engine.translate_file(src_path, lang, tgt_path)
            if summary.get("skipped"):
                print(f"[SKIP] {src_path.name} -> {lang}: {summary.get('reason', '')}")
                skip_count += 1
            else:
                cached = summary.get("cached", 0)
                translated = summary.get("translated", 0)
                print(f"[OK]   {src_path.name} -> {lang} (translated={translated}, cached={cached})")
                _write_translation_provenance(src_path, tgt_path, "page")
                ok_count += 1
        except ValidationError as e:
            first_failure = e.result.failures[0] if e.result.failures else "unknown"
            print(f"[FAIL] {src_path.name} -> {lang}: validation failed -- {first_failure}")
            fail_count += 1
        except Exception as e:
            msg = str(e).encode("ascii", errors="replace").decode("ascii")
            print(f"[FAIL] {src_path.name} -> {lang}: {msg}")
            fail_count += 1

    print(f"\nSummary: {ok_count} ok, {skip_count} skipped, {fail_count} failed")
    if fail_count > 0:
        sys.exit(1)


def _cmd_batch(args):
    engine = _build_engine(args)
    locales = _parse_locales(args.locales)
    sites = _ALL_SITES if args.site == "all" else [args.site]

    # --retry-failed mode: only re-run files that failed in a prior manifest
    retry_manifest = None
    retry_jobs = None  # set of (source_str, lang) pairs to retry
    if getattr(args, "retry_failed", None):
        manifest_path = Path(args.retry_failed)
        if not manifest_path.exists():
            print(f"Manifest not found: {manifest_path}")
            sys.exit(1)
        retry_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        retry_jobs = set()
        for _tgt, info in retry_manifest.get("files", {}).items():
            if info.get("status") == "failed":
                retry_jobs.add((info["source"], info["lang"]))
        if not retry_jobs:
            print("No failed files in manifest — nothing to retry.")
            return
        print(f"Retrying {len(retry_jobs)} previously-failed file(s) from manifest.")

    source_files = []
    for site in sites:
        site_root = _SITES.get(site)
        if not site_root:
            continue
        # blog.aspose.org uses no /en/ prefix: content/blog.aspose.org/{family}/{platform}/
        # All other sites use: content/{site}/en/{family}/{platform}/
        if site == "blog.aspose.org":
            en_root = site_root / args.family / args.platform
        else:
            en_root = site_root / "en" / args.family / args.platform
        if en_root.exists():
            source_files.extend(en_root.rglob("*.md"))

    if not source_files:
        print(f"No English source files found for family={args.family} platform={args.platform}")
        return

    total = len(source_files) * len(locales)
    done = ok_count = fail_count = skip_count = 0
    results = {}  # {target_path_str: {"status": ..., ...}}

    skip_grade = getattr(args, "skip_grade_check", False)

    for src_path in sorted(source_files):
        src_str = str(src_path).replace("\\", "/")

        # Grade-floor check (once per source file, not per locale)
        if not _check_grade_floor(src_path, skip=skip_grade):
            for lang in locales:
                tgt_path = _derive_output_path(src_path, lang)
                tgt_str = str(tgt_path).replace("\\", "/") if tgt_path else f"{src_str}:{lang}"
                results[tgt_str] = {
                    "status": "skipped", "reason": "grade_floor",
                    "source": src_str, "lang": lang,
                }
                skip_count += 1
                done += 1
            continue

        for lang in locales:
            done += 1
            tgt_path = _derive_output_path(src_path, lang)
            if tgt_path is None:
                results[f"{src_str}:{lang}"] = {"status": "skipped", "reason": "no_target_path"}
                skip_count += 1
                continue

            tgt_str = str(tgt_path).replace("\\", "/")

            # In retry-failed mode, skip any file not in the retry set
            if retry_jobs is not None:
                if (src_str, lang) not in retry_jobs:
                    # Don't record — these are intentionally excluded from this run
                    skip_count += 1
                    continue

            # Skip if translated file is newer than source (unless --force or --retry-failed)
            if not args.force and retry_jobs is None and tgt_path.exists():
                if tgt_path.stat().st_mtime >= src_path.stat().st_mtime:
                    results[tgt_str] = {
                        "status": "skipped", "reason": "mtime_current",
                        "source": src_str, "lang": lang,
                    }
                    skip_count += 1
                    continue

            try:
                summary = engine.translate_file(src_path, lang, tgt_path)
                if summary.get("skipped"):
                    results[tgt_str] = {
                        "status": "skipped", "reason": "engine_skipped",
                        "source": src_str, "lang": lang,
                    }
                    skip_count += 1
                else:
                    _write_translation_provenance(src_path, tgt_path, "batch")
                    results[tgt_str] = {
                        "status": "ok", "source": src_str, "lang": lang,
                    }
                    ok_count += 1
                    if done % 10 == 0:
                        print(f"  [{done}/{total}] {ok_count} ok, {skip_count} skipped, {fail_count} failed")
            except ValidationError as e:
                first_failure = e.result.failures[0] if e.result.failures else "validation"
                msg = str(first_failure).encode("ascii", "replace").decode()
                print(f"[FAIL] {src_path.name} -> {lang}: {msg}")
                results[tgt_str] = {
                    "status": "failed", "source": src_str, "lang": lang,
                    "error": msg,
                }
                fail_count += 1
            except Exception as e:
                msg = str(e).encode("ascii", "replace").decode()
                print(f"[FAIL] {src_path.name} -> {lang}: {msg}")
                results[tgt_str] = {
                    "status": "failed", "source": src_str, "lang": lang,
                    "error": msg,
                }
                fail_count += 1

    print(f"\nBatch complete: {ok_count} ok, {skip_count} skipped, {fail_count} failed")

    # Write batch manifest to reports/translation/ (gitignored)
    manifest = {
        "family": args.family,
        "platform": args.platform,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "locales": locales,
        "summary": {"ok": ok_count, "skipped": skip_count, "failed": fail_count},
        "files": results,
    }
    manifest_dir = _REPO_ROOT / "reports" / "translation"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    manifest_path = manifest_dir / f"{args.family}-{args.platform}-{ts}.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifest: {manifest_path}")

    if fail_count > 0:
        sys.exit(1)


def _cmd_sync(args):
    """Find and re-translate stale English to locale pairs."""
    locales = _parse_locales(args.locales)
    sites = _ALL_SITES if args.site == "all" else [args.site]

    # Find English source files
    source_files = []
    for site in sites:
        site_root = _SITES.get(site)
        if not site_root:
            continue
        # blog.aspose.org uses no /en/ prefix: content/blog.aspose.org/{family}/{platform}/
        # All other sites use: content/{site}/en/{family}/{platform}/
        if site == "blog.aspose.org":
            en_root = site_root
        else:
            en_root = site_root / "en"
        if args.family:
            en_root = en_root / args.family
        if args.platform:
            en_root = en_root / args.platform
        if en_root.exists():
            source_files.extend(en_root.rglob("*.md"))

    stale_jobs = []
    for src_path in source_files:
        for lang in locales:
            tgt_path = _derive_output_path(src_path, lang)
            if tgt_path is None:
                continue
            if not tgt_path.exists() or src_path.stat().st_mtime > tgt_path.stat().st_mtime:
                stale_jobs.append((src_path, lang, tgt_path))

    print(f"Found {len(stale_jobs)} stale translation(s)")
    if not stale_jobs:
        return

    engine = _build_engine(args)
    ok_count = fail_count = 0

    for i, (src_path, lang, tgt_path) in enumerate(stale_jobs):
        # Overwrite protection: check provenance auto_updatable flag
        if tgt_path.exists() and not _prov.is_auto_updatable(tgt_path):
            print(f"[SKIP] {tgt_path} -- auto_updatable=false, requires review")
            continue

        try:
            summary = engine.translate_file(src_path, lang, tgt_path)
            _write_translation_provenance(src_path, tgt_path, "sync")
            ok_count += 1
            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(stale_jobs)}] {ok_count} ok, {fail_count} failed")
        except Exception as e:
            msg = str(e).encode("ascii", "replace").decode()
            print(f"[FAIL] {src_path.name} -> {lang}: {msg}")
            fail_count += 1

    print(f"\nSync complete: {ok_count} ok, {fail_count} failed")


def _cmd_flush_cache(args):
    cache = TranslationCache(str(_DEFAULT_CACHE))
    lang = getattr(args, "lang", None)
    deleted = cache.flush(tgt_lang=lang)
    if lang:
        print(f"Flushed {deleted} cache entries for language '{lang}'")
    else:
        print(f"Flushed {deleted} cache entries")


def _cmd_cache_stats():
    cache = TranslationCache(str(_DEFAULT_CACHE))
    stats = cache.stats()
    print(f"Cache: {stats['total_entries']} entries, {stats['total_hits']} total hits")
    print("By language:")
    for lang, count in sorted(stats["by_language"].items()):
        print(f"  {lang}: {count}")


def _cmd_audit(args):
    """Run translation quality audit."""
    if args.quiet:
        logging.getLogger("translator.audit").setLevel(logging.WARNING)

    from translator.validation.audit import audit_translations, write_audit_report

    issues = audit_translations(
        family=args.family,
        platform=args.platform,
        site=args.site,
        locales=args.locales,
    )

    write_audit_report(issues, args.output)

    # Print summary
    critical = sum(1 for i in issues if i["severity"] == "critical")
    minor = sum(1 for i in issues if i["severity"] == "minor")
    print(f"Audit complete: {len(issues)} issues ({critical} critical, {minor} minor)")
    print(f"Report: {args.output}")

    return 0 if critical == 0 else 1


def _cmd_retranslate(args):
    """Re-translate files identified in audit report.

    Workflow per issue:
      1. Parse source file and segment body using the same protection +
         split pipeline that translate_file() uses.
      2. Flush each segment's cache entry individually (correct site_id).
      3. Call translate_file() to produce a new translated output file.
    """
    import json
    import time
    from translator.parser.document import parse_file as _parse_file
    from translator.engine.translator import segment_body_for_cache, extract_site_id

    if getattr(args, "quiet", False):
        logging.getLogger("translator.audit").setLevel(logging.WARNING)

    report_path = Path(args.report)
    if not report_path.exists():
        logger.error("Report not found: %s", report_path)
        return 1

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    issues = report.get("issues", [])
    if args.severity != "all":
        severity_order = {"critical": 0, "minor": 1}
        threshold = severity_order.get(args.severity, 0)
        issues = [i for i in issues if severity_order.get(i["severity"], 99) <= threshold]

    if not issues:
        logger.info("retranslate: no issues match severity filter '%s'", args.severity)
        return 0

    max_per_run = getattr(args, "max_per_run", 100)
    delay_seconds = getattr(args, "delay_seconds", 0.5)
    logger.info("retranslate: %d files queued for re-translation (max-per-run=%d)",
                len(issues), max_per_run)

    if args.dry_run:
        for issue in issues[:max_per_run]:
            print(f"  [DRY RUN] Would retranslate: {issue['file']} ({issue['lang']})")
        return 0

    engine = _build_engine(args)
    cache = engine.cache
    processed = ok_count = fail_count = 0

    for issue in issues:
        if processed >= max_per_run:
            logger.info("retranslate: reached --max-per-run %d, stopping", max_per_run)
            break

        src_file = issue.get("src_file")
        lang = issue.get("lang", "")

        if not src_file:
            processed += 1
            continue

        src_path = Path(src_file)
        if not src_path.exists():
            logger.warning("retranslate: source file not found: %s", src_file)
            processed += 1
            continue

        # Step 1: Flush cache using segment-level keys (matches translate_file)
        try:
            src_doc = _parse_file(src_path)
            site_id = extract_site_id(src_path)
            segments = segment_body_for_cache(src_doc.body, src_path)
            deleted = 0
            for seg in segments:
                if not seg.strip():
                    continue
                deleted += cache.flush_for_source(site_id, lang, seg)
            logger.info("retranslate: flushed %d cache entries for %s [%s]",
                        deleted, src_file, lang)
        except Exception as e:
            logger.warning("retranslate: cache flush failed for %s: %s", src_file, e)

        # Step 2: Re-translate the file
        tgt_path = _derive_output_path(src_path, lang)
        if tgt_path is None:
            logger.warning("retranslate: cannot derive output path for %s -> %s",
                           src_file, lang)
            processed += 1
            continue

        try:
            summary = engine.translate_file(src_path, lang, tgt_path)
            cached = summary.get("cached", 0)
            translated = summary.get("translated", 0)
            logger.info("retranslate: %s -> %s (translated=%d, cached=%d)",
                        src_file, lang, translated, cached)
            _write_translation_provenance(src_path, tgt_path, "retranslate")
            ok_count += 1
        except ValidationError as e:
            first_failure = e.result.failures[0] if e.result.failures else "unknown"
            logger.warning("retranslate: validation failed for %s [%s]: %s",
                           src_file, lang, first_failure)
            fail_count += 1
        except Exception as e:
            logger.warning("retranslate: failed %s [%s]: %s", src_file, lang, e)
            fail_count += 1

        processed += 1
        logger.info("retranslate: completed %d/%d files",
                    processed, min(len(issues), max_per_run))

        if delay_seconds > 0 and processed < max_per_run:
            time.sleep(delay_seconds)

    print(f"\nRetranslate complete: {ok_count} ok, {fail_count} failed, "
          f"{processed} processed (max {max_per_run})")
    return 0 if fail_count == 0 else 1


def _derive_output_path(src_path: Path, lang: str) -> Path | None:
    """
    Derive the output path for a translated file.

    - For directory-based sites (docs/kb/products/reference): replaces '/en/' with '/{lang}/'.
    - For blog (filename-based): replaces trailing 'index.md' with 'index.{lang}.md'.
    """
    path_str = str(src_path).replace("\\", "/")

    # Blog uses filename-based translations: index.md -> index.{lang}.md
    if "blog.aspose.org" in path_str:
        if path_str.endswith("/index.md"):
            tgt_str = path_str[:-len("index.md")] + f"index.{lang}.md"
            return Path(tgt_str)
        return None

    # All other sites use directory-based translations via /en/ prefix
    if "/en/" not in path_str:
        return None
    tgt_str = path_str.replace("/en/", f"/{lang}/", 1)
    return Path(tgt_str)


if __name__ == "__main__":
    main()
