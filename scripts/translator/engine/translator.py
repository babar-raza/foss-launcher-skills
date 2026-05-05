"""
TranslationEngine: orchestrates the full translation workflow for a Hugo .md file.

Workflow:
  parse → extract fields → protect body → cache-check → translate → restore → validate → write
"""
from __future__ import annotations
import copy
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import (
    FrontmatterParseError, PlaceholderLeakError, TranslatorError,
    ALL_LOCALES, LOCALE_NAMES,
)
from translator.policy.loader import ContentTypePolicy
from translator.parser.document import parse_file, HugoDocument
from translator.parser.frontmatter import iter_translatable_fields, set_field
from translator.parser.protector import protect, restore
from translator.backends.base import TranslationBackend, BackendRouter
from translator.cache.sqlite_cache import TranslationCache
from translator.writer.reconstructor import reconstruct_and_write
from translator.validation.checker import validate_translation, ValidationResult
from translator.postprocess.punctuation import normalize_punctuation

logger = logging.getLogger(__name__)

_PLACEHOLDER_TOKEN_RE = re.compile(r'⟦PH_\d{4}⟧')


class ValidationError(TranslatorError):
    """Raised when post-translation validation fails."""
    def __init__(self, result: ValidationResult):
        self.result = result
        super().__init__(f"Translation validation failed: {'; '.join(result.failures)}")


class TranslationEngine:
    """
    Orchestrates translation of a single Hugo .md file to a target language.
    """

    def __init__(
        self,
        backend: TranslationBackend | BackendRouter,
        cache: TranslationCache,
        dry_run: bool = False,
    ):
        self.backend = backend
        self.cache = cache
        self.dry_run = dry_run

    def translate_file(
        self,
        src_path: str | Path,
        tgt_lang: str,
        output_path: str | Path,
    ) -> dict:
        """
        Translate src_path to tgt_lang and write to output_path.

        Returns a summary dict with keys: skipped, translated, cached, validation.
        Raises ValidationError if validation fails.
        Raises PlaceholderLeakError if body placeholder restoration fails.
        """
        src_path = Path(src_path)
        output_path = Path(output_path)

        # Step 1: Load policy
        try:
            policy = ContentTypePolicy.for_path(str(src_path))
        except ValueError as e:
            logger.warning(f"Cannot determine content type for {src_path}: {e}")
            return {"skipped": True, "reason": "unknown_content_type"}

        # Step 2: Skip if policy marks content as non-translatable
        if policy.skip:
            logger.debug(f"Skipping {src_path} (policy: skip=True)")
            return {"skipped": True, "reason": "policy_skip"}

        # Step 3: Parse document
        src_doc = parse_file(src_path)

        # Step 4: Preserve evidence block exactly via deep copy
        evidence_original = copy.deepcopy(src_doc.frontmatter.get("evidence"))

        # Step 5: Extract translatable frontmatter fields
        fm_pairs = list(iter_translatable_fields(
            src_doc.frontmatter,
            policy.field_policy.translate,
            policy.field_policy.translate_nested,
        ))

        # Step 6: Protect body with placeholder tokens
        site_id = _extract_site_id(src_path)
        protected_body, placeholder_map = protect(
            src_doc.body,
            policy.protected_patterns,
            policy.placeholder_format,
        )

        # Split protected body into translatable segments (paragraph-level)
        body_segments = _split_segments(protected_body)

        # Step 7: Translate via cache → backend
        summary = {"skipped": False, "translated": 0, "cached": 0, "validation": None}

        # Translate frontmatter fields
        translated_fm = copy.deepcopy(src_doc.frontmatter)
        for path, value in fm_pairs:
            # Skip evidence field — it must never be sent to the backend
            if path == "evidence" or path.startswith("evidence.") or path.startswith("evidence["):
                continue
            cached = self.cache.lookup(site_id, "en", tgt_lang, value)
            if cached is not None:
                summary["cached"] += 1
                set_field(translated_fm, path, cached)
            else:
                if not self.dry_run:
                    translation = self.backend.translate(value, "en", tgt_lang)
                    self.cache.store(
                        site_id, "en", tgt_lang, value, translation,
                        self._backend_model_id(),
                    )
                    set_field(translated_fm, path, translation)
                summary["translated"] += 1

        # Translate body segments with document context
        translated_segments = []
        doc_title = src_doc.frontmatter.get("title", "")
        heading_outline = _extract_heading_outline(protected_body)
        prev_translated = ""
        use_context = hasattr(self.backend, "translate_with_context")

        for seg in body_segments:
            if not seg.strip():
                translated_segments.append(seg)
                continue
            if _is_pure_placeholder(seg):
                translated_segments.append(seg)
                continue
            cached = self.cache.lookup(site_id, "en", tgt_lang, seg)
            if cached is not None:
                summary["cached"] += 1
                translated_segments.append(cached)
                prev_translated = cached
            else:
                if not self.dry_run:
                    if use_context:
                        translation = self.backend.translate_with_context(
                            seg, "en", tgt_lang,
                            document_title=doc_title,
                            heading_outline=heading_outline,
                            prev_segment=prev_translated,
                        )
                    else:
                        translation = self.backend.translate(seg, "en", tgt_lang)
                    self.cache.store(
                        site_id, "en", tgt_lang, seg, translation,
                        self._backend_model_id(),
                    )
                    translated_segments.append(translation)
                    prev_translated = translation
                else:
                    translated_segments.append(seg)
                summary["translated"] += 1

        translated_protected_body = "\n\n".join(translated_segments)

        # Step 8: Restore placeholders (raises PlaceholderLeakError if any are missing)
        translated_body = restore(translated_protected_body, placeholder_map)

        # Step 8b: Normalize CJK punctuation artifacts
        translated_body = normalize_punctuation(translated_body, tgt_lang)

        # Step 9: Re-inject evidence block — must be identical to source
        if evidence_original is not None:
            translated_fm["evidence"] = evidence_original

        # Step 10: Build translated document
        tgt_doc = HugoDocument(
            frontmatter=translated_fm,
            body=translated_body,
            source_path=src_path,
        )

        # Step 11: Run post-translation validation
        # In dry-run mode, body is untranslated English — skip language-specific checks
        validation_lang = tgt_lang if not self.dry_run else ""
        result = validate_translation(src_doc, tgt_doc, policy, validation_lang)
        summary["validation"] = result

        if not result.passed:
            logger.error(
                f"Validation failed for {src_path} → {tgt_lang}: {result.failures}"
            )
            raise ValidationError(result)

        # Step 12: Write output atomically
        if not self.dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            reconstruct_and_write(tgt_doc, output_path)
            logger.info(f"Written: {output_path}")
        else:
            logger.info(f"[DRY RUN] Would write: {output_path}")

        return summary

    def _backend_model_id(self) -> str:
        """Return the active backend's model identifier for cache provenance."""
        try:
            if isinstance(self.backend, BackendRouter):
                info = self.backend.active_backend_info()
                if info:
                    return info.get("model", "unknown")
                return "unknown"
            elif hasattr(self.backend, "get_model_info"):
                info = self.backend.get_model_info()
                return info.get("model", "unknown")
        except Exception:
            pass
        return "unknown"


def extract_site_id(path: Path) -> str:
    """Extract site ID from a content path, e.g. 'docs.aspose.org'."""
    path_str = str(path).replace("\\", "/")
    for site in [
        "docs.aspose.org",
        "kb.aspose.org",
        "products.aspose.org",
        "reference.aspose.org",
        "blog.aspose.org",
    ]:
        if site in path_str:
            return site
    return "unknown"


# Keep private alias for internal use
_extract_site_id = extract_site_id


def _split_segments(text: str) -> list[str]:
    """Split body text into translatable segments on double newlines."""
    return text.split("\n\n")


def segment_body_for_cache(body: str, src_path: str | Path) -> list[str]:
    """Replicate the exact segmentation pipeline used by translate_file().

    Applies placeholder protection then splits into paragraph-level segments,
    matching the cache keys that translate_file() stores.
    """
    src_path = Path(src_path)
    policy = ContentTypePolicy.for_path(str(src_path))
    protected_body, _ = protect(body, policy.protected_patterns, policy.placeholder_format)
    return _split_segments(protected_body)


def _is_pure_placeholder(seg: str) -> bool:
    """Return True if segment contains only placeholder tokens and whitespace."""
    cleaned = _PLACEHOLDER_TOKEN_RE.sub("", seg).strip()
    return not cleaned


def _extract_heading_outline(body: str) -> str:
    """Extract markdown headings as a structural outline."""
    headings = re.findall(r'^(#{1,6}\s+.+)$', body, re.MULTILINE)
    return "\n".join(headings)
