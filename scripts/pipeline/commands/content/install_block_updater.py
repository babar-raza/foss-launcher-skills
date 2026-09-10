"""
install_block_updater.py — TC-05: Apply install command changes to English content pages.

Handles INSTALL_CMD_ADDED, INSTALL_CMD_CHANGED, and VERSION_BUMP events from
manifest_delta.json by locating and replacing install command blocks in content pages.

Reads the authoritative install command from merged/install.md (NOT model.yaml, which
lacks install_command after promote.py strips it — see AF-03).

English-only enforcement: uses _target_locale_verdict() from body_refresh.py.

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.install_block_updater 3d net
    PYTHONPATH=scripts/pipeline python -m commands.content.install_block_updater 3d net --dry-run
    PYTHONPATH=scripts/pipeline python -m commands.content.install_block_updater 3d net --execute

Platform-specific matchers:
    Python:  pip install {name}>={version}  -- case-sensitive
    .NET:    dotnet add package {name} --version {version}  -- case-INSENSITIVE (AF-06)
    Java:    <groupId>...</groupId> + <artifactId>...</artifactId> block (Maven XML)
    JS:      npm install {name}@{version}  -- case-sensitive
    Go:      go get {module}  -- case-sensitive
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any

# ── Path constants ─────────────────────────────────────────────────────────

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
_CONTENT_ROOT = _REPO_ROOT / "content"
_REPORTS_ROOT = _REPO_ROOT / "reports"

# ── Configuration seam ─────────────────────────────────────────────────────

def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Reconfigure module paths (used by tests)."""
    global _REPO_ROOT, _KNOWLEDGE_ROOT, _CONTENT_ROOT, _REPORTS_ROOT
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
        _KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
        _CONTENT_ROOT = _REPO_ROOT / "content"
        _REPORTS_ROOT = _REPO_ROOT / "reports"


# ── Result constants ────────────────────────────────────────────────────────

R_UPDATED = "INSTALL_BLOCK_UPDATED"
R_ADDED = "INSTALL_BLOCK_ADDED"
R_NOOP = "NOOP_ALREADY_CURRENT"
R_SKIPPED_LOCALE = "SKIPPED_LOCALE"
R_SKIPPED_PROTECTED = "SKIPPED_PROTECTED"
R_SKIPPED_NO_BLOCK = "SKIPPED_NO_INSTALL_BLOCK"
R_HUMAN_REVIEW = "HUMAN_REVIEW_REQUIRED"
R_DRY_RUN = "DRY_RUN"
R_NO_MANIFEST_DELTA = "NO_MANIFEST_DELTA"
R_NO_RELEVANT_EVENT = "NO_RELEVANT_EVENT"


# ── Install block parsing ──────────────────────────────────────────────────

def _parse_install_md(install_path: Path) -> dict[str, str]:
    """Parse merged/install.md to extract package identifiers.

    Returns dict with keys: install_block, package_name, version,
    group_id, artifact_id. All values are strings (empty string if absent).
    """
    result: dict[str, str] = {
        "install_block": "",
        "package_name": "",
        "version": "",
        "group_id": "",
        "artifact_id": "",
    }
    if not install_path.is_file():
        return result

    text = install_path.read_text(encoding="utf-8", errors="replace")

    # Extract first fenced code block
    code_block_match = re.search(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    if not code_block_match:
        return result

    block = code_block_match.group(1).strip()
    result["install_block"] = block

    # Python: pip install {name}>={version} or pip install {name}=={version}
    m = re.match(r"pip install\s+([A-Za-z0-9._-]+)(?:[>=<]+([A-Za-z0-9._-]+))?", block)
    if m:
        result["package_name"] = m.group(1)
        result["version"] = m.group(2) or ""
        return result

    # .NET: dotnet add package {name} --version {version}
    m = re.match(
        r"dotnet add package\s+([A-Za-z0-9._-]+)(?:\s+--version\s+([A-Za-z0-9._-]+))?",
        block,
        re.IGNORECASE,
    )
    if m:
        result["package_name"] = m.group(1)
        result["version"] = m.group(2) or ""
        return result

    # Java Maven XML
    gid = re.search(r"<groupId>([^<]+)</groupId>", block)
    aid = re.search(r"<artifactId>([^<]+)</artifactId>", block)
    ver = re.search(r"<version>([^<]+)</version>", block)
    if gid or aid:
        result["group_id"] = gid.group(1).strip() if gid else ""
        result["artifact_id"] = aid.group(1).strip() if aid else ""
        result["version"] = ver.group(1).strip() if ver else ""
        result["package_name"] = result["artifact_id"]
        return result

    # JavaScript: npm install {name}@{version}
    # TC-MT040-46: the old character class ([A-Za-z0-9@._/-]) included "@"
    # inside group 1 itself, so for a real scoped-package command like
    # "npm install @asposefoss/pdf@0.1.0" group 1 greedily swallowed the
    # ENTIRE string including the trailing "@0.1.0" version, leaving
    # version empty and package_name wrong ("@asposefoss/pdf@0.1.0" instead
    # of "@asposefoss/pdf"). Fixed to structurally separate an optional
    # leading "@scope/" segment (which itself contains no further "@") from
    # the package's base name, so the trailing "(?:@version)?" group is the
    # ONLY place a second "@" can be consumed from. Verified against all
    # three real shapes: a scoped name with a version
    # ("@asposefoss/pdf@0.1.0" -> name="@asposefoss/pdf", version="0.1.0"),
    # the pre-existing unscoped case ("aspose-3d@24.12.0" -> unchanged), and
    # a scoped name with no version ("@asposefoss/pdf" -> version="").
    m = re.match(r"npm install\s+((?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+)(?:@([A-Za-z0-9._-]+))?", block)
    if m:
        result["package_name"] = m.group(1)
        result["version"] = m.group(2) or ""
        return result

    # Go: go get {module}
    m = re.match(r"go get\s+(\S+)", block)
    if m:
        result["package_name"] = m.group(1)
        return result

    # Rust: cargo add {crate}@{version}
    m = re.match(r"cargo add\s+([A-Za-z0-9._-]+)(?:@([A-Za-z0-9._-]+))?", block)
    if m:
        result["package_name"] = m.group(1)
        result["version"] = m.group(2) or ""
        return result

    # Rust: Cargo.toml git-dependency form ({crate} = { git = "..." }),
    # emitted by outputs.py while the crate is unpublished on crates.io.
    m = re.search(
        r'^([A-Za-z0-9._-]+)\s*=\s*\{\s*git\s*=\s*"[^"]+"', block, re.MULTILINE)
    if m:
        result["package_name"] = m.group(1)
        return result

    return result


# ── Platform detection ─────────────────────────────────────────────────────

_PLATFORM_DOTNET = frozenset({"net", "cpp"})
_PLATFORM_JAVA = frozenset({"java"})
_PLATFORM_PYTHON = frozenset({"python"})
_PLATFORM_JS = frozenset({"typescript", "javascript", "nodejs"})
_PLATFORM_GO = frozenset({"go"})
_PLATFORM_RUST = frozenset({"rust"})


def _detect_platform_type(platform: str) -> str:
    """Map platform string to install system type."""
    p = platform.lower()
    if p in _PLATFORM_DOTNET:
        return "dotnet"
    if p in _PLATFORM_JAVA:
        return "java"
    if p in _PLATFORM_PYTHON:
        return "python"
    if p in _PLATFORM_JS:
        return "js"
    if p in _PLATFORM_GO:
        return "go"
    if p in _PLATFORM_RUST:
        return "rust"
    return "unknown"


# ── Code block extraction ──────────────────────────────────────────────────

def _extract_fenced_blocks(content: str) -> list[tuple[int, int, str, str]]:
    """Return list of (start_pos, end_pos, lang, block_text) for all fenced code blocks.

    Positions are inclusive character offsets into content.
    block_text includes the opening and closing fence lines.
    """
    results = []
    # Match ``` or ~~~ fences with optional language hint
    pattern = re.compile(r"(```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~)", re.DOTALL)
    for m in pattern.finditer(content):
        full = m.group(0)
        # Extract language hint from first line
        first_line = full.split("\n", 1)[0]
        lang = first_line.lstrip("`~").strip()
        results.append((m.start(), m.end(), lang, full))
    return results


def _block_contains_install(block_text: str, info: dict[str, str], platform_type: str) -> bool:
    """Return True if block_text contains the install command for the given platform/info."""
    inner = block_text  # includes fences, but search inside is fine

    if platform_type == "dotnet":
        # Case-insensitive match for .NET package names (AF-06)
        pkg = info.get("package_name", "")
        if pkg and re.search(
            r"dotnet add package\s+" + re.escape(pkg),
            inner,
            re.IGNORECASE,
        ):
            return True
        # Also match Install-Package (Package Manager Console style)
        if pkg and re.search(
            r"Install-Package\s+" + re.escape(pkg),
            inner,
            re.IGNORECASE,
        ):
            return True
        # Match any dotnet add package block (generic .NET install detect)
        if re.search(r"dotnet add package\s+\S+", inner, re.IGNORECASE):
            return True
        if re.search(r"Install-Package\s+\S+", inner, re.IGNORECASE):
            return True

    elif platform_type == "java":
        gid = info.get("group_id", "")
        aid = info.get("artifact_id", "")
        if gid and re.search(r"<groupId>[^<]*</groupId>", inner):
            return True
        if aid and re.search(r"<artifactId>[^<]*</artifactId>", inner):
            return True

    elif platform_type == "python":
        pkg = info.get("package_name", "")
        if pkg and re.search(r"pip install\s+" + re.escape(pkg), inner):
            return True
        if re.search(r"pip install\s+\S+", inner):
            return True

    elif platform_type == "js":
        pkg = info.get("package_name", "")
        if pkg and re.search(r"npm install\s+.*" + re.escape(pkg), inner):
            return True
        if re.search(r"npm install\s+\S+", inner):
            return True

    elif platform_type == "go":
        mod = info.get("package_name", "")
        if mod and re.search(r"go get\s+" + re.escape(mod), inner):
            return True
        if re.search(r"go get\s+\S+", inner):
            return True

    elif platform_type == "rust":
        pkg = info.get("package_name", "")
        if pkg and re.search(r"cargo add\s+" + re.escape(pkg), inner):
            return True
        if pkg and re.search(
                re.escape(pkg) + r'\s*=\s*\{\s*git\s*=', inner):
            return True
        if re.search(r"cargo add\s+\S+", inner):
            return True
        if re.search(r'\[dependencies\]', inner):
            return True

    return False


def _content_already_matches(content: str, new_info: dict[str, str], platform_type: str) -> bool:
    """Return True if content already contains the correct install block (noop)."""
    new_pkg = new_info.get("package_name", "")
    new_ver = new_info.get("version", "")
    new_gid = new_info.get("group_id", "")
    new_aid = new_info.get("artifact_id", "")

    if platform_type == "dotnet":
        if new_pkg and new_ver:
            # Case-insensitive package name match + exact version
            return bool(re.search(
                r"dotnet add package\s+" + re.escape(new_pkg) + r"\s+--version\s+" + re.escape(new_ver),
                content,
                re.IGNORECASE,
            ))

    elif platform_type == "java":
        if new_gid and new_aid and new_ver:
            return (
                new_gid in content
                and new_aid in content
                and f"<version>{new_ver}</version>" in content
            )

    elif platform_type == "python":
        if new_pkg and new_ver:
            return bool(re.search(
                r"pip install\s+" + re.escape(new_pkg) + r"[>=<]+" + re.escape(new_ver),
                content,
            ))

    elif platform_type == "js":
        if new_pkg and new_ver:
            return bool(re.search(
                r"npm install\s+.*" + re.escape(new_pkg) + r"@" + re.escape(new_ver),
                content,
            ))

    elif platform_type == "go":
        mod = new_info.get("package_name", "")
        if mod:
            return bool(re.search(r"go get\s+" + re.escape(mod), content))

    elif platform_type == "rust":
        if new_pkg and new_ver:
            return bool(re.search(
                r"cargo add\s+" + re.escape(new_pkg) + r"@" + re.escape(new_ver),
                content,
            ))
        if new_pkg:
            # Git-dependency form carries no version — package name match only
            return bool(re.search(
                re.escape(new_pkg) + r'\s*=\s*\{\s*git\s*=', content))

    return False


# ── Prose mention scanner ──────────────────────────────────────────────────

def _find_prose_install_mentions(
    content: str, info: dict[str, str], platform_type: str
) -> list[tuple[int, str]]:
    """Find old package name/coordinate mentions in PROSE (outside code blocks).

    Returns list of (line_number, line_text) for lines that mention old identifiers
    outside fenced code blocks.
    """
    # Build set of fence ranges to exclude
    blocks = _extract_fenced_blocks(content)
    fenced_ranges = {(s, e) for s, e, _, _ in blocks}

    def in_fence(char_pos: int) -> bool:
        return any(s <= char_pos < e for s, e in fenced_ranges)

    lines = content.splitlines()
    char_pos = 0
    findings: list[tuple[int, str]] = []
    pkg = info.get("package_name", "")
    gid = info.get("group_id", "")
    aid = info.get("artifact_id", "")

    for ln_idx, line in enumerate(lines, start=1):
        line_start = char_pos
        # Check if this line is entirely within a fenced block
        line_end = line_start + len(line)
        if in_fence(line_start):
            char_pos += len(line) + 1
            continue

        # Check for identifiers (but not inside inline code)
        stripped_of_inline = re.sub(r"`[^`]*`", "", line)
        found = False
        if pkg and pkg.lower() in stripped_of_inline.lower():
            found = True
        elif gid and gid in stripped_of_inline:
            found = True
        elif aid and aid in stripped_of_inline:
            found = True

        if found:
            findings.append((ln_idx, line))

        char_pos += len(line) + 1

    return findings


# ── Core updater ───────────────────────────────────────────────────────────

# ST-054 TC-03 (2026-09-10): shortcode-name per registry_type, mirroring
# package_install_migrator.py's own shortcode-construction logic exactly
# (`shortcode = f'{{< package-install "{family}" "{platform}" >}}'`) so this
# updater and that migrator never diverge on what a given registry_type
# should render as.
_SHORTCODE_BY_REGISTRY_TYPE = {
    "maven": "maven-coord",
    "cargo": "cargo-crate",
    "pypi": "package-install",
    "nuget": "package-install",
    "npm": "package-install",
    "go_modules": "package-install",
}

_INSTALL_SHORTCODE_RE = re.compile(
    r"\{\{<\s*(package-install-inline|package-install|maven-coord|maven-gav|cargo-crate)\b"
)


def _has_install_shortcode(content: str) -> bool:
    """True if content already contains any install-rendering shortcode call
    anywhere -- ST-054 TC-03. A page in this state is self-updating at Hugo
    build time; a future manifest-delta event (INSTALL_CMD_ADDED/CHANGED,
    VERSION_BUMP) has nothing left to do to it."""
    return bool(_INSTALL_SHORTCODE_RE.search(content))


def _registry_entry_for(family: str, platform: str) -> "dict | None":
    """Load data/package_registry.json and return this family/platform's
    entry, or None if the registry can't be loaded or has no such entry.
    Never raises -- a lookup failure here must degrade to the pre-TC-03
    literal-block behavior, not crash the updater."""
    try:
        from package_registry_data import load_registry
    except ImportError:
        return None
    try:
        data = load_registry(_REPO_ROOT / "data" / "package_registry.json")
    except (OSError, FileNotFoundError, ValueError):
        return None
    return (data.get(family) or {}).get(platform)


def _shortcode_call_for(family: str, platform: str, entry: dict) -> str:
    """Return the shortcode-call replacement text for this entry's
    registry_type, or "" for an unrecognized type (caller falls back to the
    literal-block behavior in that case)."""
    shortcode = _SHORTCODE_BY_REGISTRY_TYPE.get(entry.get("registry_type", ""))
    if not shortcode:
        return ""
    return f'{{{{< {shortcode} "{family}" "{platform}" >}}}}'


def _build_new_block(new_info: dict[str, str], platform_type: str, old_block: str) -> str:
    """Build the replacement fenced code block from new install info.

    Preserves the fence style (```) and language hint of the old block if possible.
    The inner content comes entirely from new_info['install_block'].
    """
    # Detect old fence style
    first_line = old_block.split("\n", 1)[0]
    fence_char = "```" if old_block.startswith("```") else "~~~"
    lang_hint = first_line.lstrip("`~").strip()
    # For install commands, lang is typically 'bash' or empty
    fence_open = fence_char + (lang_hint if lang_hint else "")

    new_inner = new_info["install_block"]
    return f"{fence_open}\n{new_inner}\n{fence_char}"


def update_install_blocks(
    page_path: Path,
    new_info: dict[str, str],
    platform_type: str,
    *,
    dry_run: bool = True,
    family: str = "",
    platform: str = "",
) -> dict[str, Any]:
    """Apply install block update to a single content page.

    Returns a result dict with keys: path, result, blocks_updated, prose_mentions.
    """
    result: dict[str, Any] = {
        "path": str(page_path),
        "result": R_NOOP,
        "blocks_updated": 0,
        "prose_mentions": 0,
        "error": "",
    }

    if not page_path.is_file():
        result["result"] = R_SKIPPED_NO_BLOCK
        result["error"] = "file not found"
        return result

    # English-only guard
    if family and platform:
        try:
            from commands.content.body_refresh import _target_locale_verdict
            allowed, locale, reason = _target_locale_verdict(str(page_path), family, platform)
            if not allowed:
                result["result"] = R_SKIPPED_LOCALE
                result["error"] = f"{reason} (locale={locale})"
                return result
        except ImportError:
            # Fallback locale check: reject paths with locale-suffixed filenames
            fname = page_path.name
            if re.search(r"\.[a-z]{2}(?:-[a-z0-9]{2,4})?\.md$", fname):
                result["result"] = R_SKIPPED_LOCALE
                result["error"] = "locale-suffixed filename"
                return result
            # Reject paths not under /en/
            path_str = str(page_path)
            if (
                "/docs.aspose.org/" in path_str
                or "/kb.aspose.org/" in path_str
                or "/reference.aspose.org/" in path_str
                or "/products.aspose.org/" in path_str
            ) and "/en/" not in path_str:
                result["result"] = R_SKIPPED_LOCALE
                result["error"] = "not under /en/ directory"
                return result

    content = page_path.read_text(encoding="utf-8", errors="replace")

    # ST-054 TC-03: a page already rendering its install command via shortcode
    # is self-updating at Hugo build time -- a manifest-delta event (version
    # bump, publish-state change) has nothing left to do to it, and must not
    # fall through to the literal-block logic below (which has no shortcode
    # calls to find and would report SKIPPED_NO_INSTALL_BLOCK instead of the
    # more accurate NOOP_ALREADY_CURRENT).
    if _has_install_shortcode(content):
        result["result"] = R_NOOP
        return result

    # Noop check: if content already has the correct install block
    if _content_already_matches(content, new_info, platform_type):
        result["result"] = R_NOOP
        return result

    # Find install code blocks to replace
    blocks = _extract_fenced_blocks(content)
    install_blocks = [
        (s, e, lang, txt)
        for s, e, lang, txt in blocks
        if _block_contains_install(txt, new_info, platform_type)
    ]

    if not install_blocks:
        # No install block found — this page doesn't contain the install command
        result["result"] = R_SKIPPED_NO_BLOCK
        return result

    # Check for protected page
    if "auto_updatable: false" in content:
        result["result"] = R_SKIPPED_PROTECTED
        return result

    # ST-054 TC-03: prefer migrating straight to the shortcode call over
    # regenerating another literal block, whenever a registry entry exists to
    # ground it -- this is the durability fix itself: without it, every future
    # manifest-delta event would keep re-writing literal text for a page ST-054's
    # migration (TC-06) hasn't reached yet, undoing that migration's own work on
    # its next run. Falls back to the pre-TC-03 literal-block behavior when no
    # entry exists (unregistered family/platform), matching this module's
    # existing fail-open-to-old-behavior posture elsewhere in this function.
    registry_entry = _registry_entry_for(family, platform) if family and platform else None
    shortcode_call = (
        _shortcode_call_for(family, platform, registry_entry) if registry_entry else ""
    )

    # Build updated content by replacing install blocks (last-to-first to preserve offsets)
    updated = content
    blocks_updated = 0
    for s, e, lang, old_block in reversed(install_blocks):
        if shortcode_call:
            new_block = shortcode_call
        else:
            new_block = _build_new_block(new_info, platform_type, old_block)
        updated = updated[:s] + new_block + updated[e:]
        blocks_updated += 1

    result["blocks_updated"] = blocks_updated

    # Scan for prose mentions of old identifiers (outside code blocks)
    prose_mentions = _find_prose_install_mentions(updated, new_info, platform_type)
    if prose_mentions:
        result["prose_mentions"] = len(prose_mentions)
        # We still write the code-block fix, but flag prose for human review
        result["result"] = R_HUMAN_REVIEW

    if blocks_updated > 0 and result["result"] == R_NOOP:
        result["result"] = R_UPDATED

    if dry_run:
        if result["result"] in (R_UPDATED, R_HUMAN_REVIEW):
            result["result"] = R_DRY_RUN
        return result

    # Write the updated content
    if blocks_updated > 0 and updated != content:
        try:
            from lib.provenance import safe_content_write
            safe_content_write(page_path, updated, mechanism="install-block-updater")
        except ImportError:
            page_path.write_text(updated, encoding="utf-8")
        except Exception as exc:
            if "ProtectedPageError" in type(exc).__name__:
                result["result"] = R_SKIPPED_PROTECTED
                result["error"] = str(exc)
                return result
            raise

        if prose_mentions:
            result["result"] = R_HUMAN_REVIEW
        else:
            result["result"] = R_UPDATED

    return result


# ── Region-indexed updater ─────────────────────────────────────────────────

def run_update(
    family: str,
    platform: str,
    *,
    dry_run: bool = True,
    manifest_delta_path: "Path | None" = None,
) -> dict[str, Any]:
    """Run install block updates for a product using the region index and manifest delta.

    Returns a summary dict with per-file results.
    """
    summary: dict[str, Any] = {
        "family": family,
        "platform": platform,
        "dry_run": dry_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event": "",
        "files_checked": 0,
        "files_updated": 0,
        "files_noop": 0,
        "files_skipped": 0,
        "human_review_required": [],
        "results": [],
    }

    # 1. Load manifest_delta.json to determine the event type and new coordinates
    if manifest_delta_path is None:
        manifest_delta_path = _KNOWLEDGE_ROOT / family / platform / "merged" / "manifest_delta.json"

    if not manifest_delta_path.is_file():
        summary["event"] = R_NO_MANIFEST_DELTA
        return summary

    delta = json.loads(manifest_delta_path.read_text(encoding="utf-8"))
    events = delta.get("install_cmd_changes", []) + delta.get("coordinate_changes", []) + delta.get("version_changes", [])

    if not events:
        summary["event"] = R_NO_RELEVANT_EVENT
        return summary

    # Pick the primary event (first one wins)
    primary_event = events[0]
    summary["event"] = primary_event.get("change_type", "UNKNOWN")

    # 2. Load new install info from merged/install.md (authoritative source — AF-03)
    install_md_path = _KNOWLEDGE_ROOT / family / platform / "merged" / "install.md"
    new_info = _parse_install_md(install_md_path)

    if not new_info.get("install_block"):
        summary["event"] = "NO_INSTALL_BLOCK_IN_KNOWLEDGE"
        return summary

    platform_type = _detect_platform_type(platform)

    # 3. Load content region index to find affected files
    region_index_path = _REPORTS_ROOT / "content_region_index" / f"{family}_{platform}.json"
    if not region_index_path.is_file():
        # Fall back: scan all content pages for this product
        target_files = list(
            (_CONTENT_ROOT / "docs.aspose.org" / "en" / family / platform).rglob("*.md")
        ) + list(
            (_CONTENT_ROOT / "kb.aspose.org" / "en" / family / platform).rglob("*.md")
        )
    else:
        region_data = json.loads(region_index_path.read_text(encoding="utf-8"))
        install_pages = region_data.get("install_command_blocks", [])
        target_files = [_REPO_ROOT / p for p in install_pages]

    # 4. Apply updates
    for page_path in target_files:
        page_path = Path(page_path)
        if not page_path.exists():
            continue

        summary["files_checked"] += 1
        res = update_install_blocks(
            page_path,
            new_info,
            platform_type,
            dry_run=dry_run,
            family=family,
            platform=platform,
        )
        summary["results"].append(res)

        r = res["result"]
        if r in (R_UPDATED, R_HUMAN_REVIEW):
            summary["files_updated"] += 1
            if r == R_HUMAN_REVIEW:
                summary["human_review_required"].append(str(page_path))
        elif r == R_NOOP:
            summary["files_noop"] += 1
        elif r == R_DRY_RUN:
            summary["files_updated"] += 1
        else:
            summary["files_skipped"] += 1

    return summary


# ── CLI ────────────────────────────────────────────────────────────────────

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="install_block_updater",
        description="Update install command blocks in English content pages from manifest_delta.json.",
    )
    parser.add_argument("family", nargs="?", help="Product family (e.g. 3d)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. net)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without writing (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write changes to disk",
    )
    parser.add_argument(
        "--manifest-delta",
        metavar="PATH",
        help="Override path to manifest_delta.json",
    )
    args = parser.parse_args(argv)

    if not args.family or not args.platform:
        parser.print_help()
        return 1

    dry_run = not args.execute

    manifest_delta_path = Path(args.manifest_delta) if args.manifest_delta else None

    summary = run_update(
        args.family,
        args.platform,
        dry_run=dry_run,
        manifest_delta_path=manifest_delta_path,
    )

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\ninstall_block_updater [{mode}] {args.family}/{args.platform}")
    print(f"  event:         {summary['event']}")
    print(f"  files_checked: {summary['files_checked']}")
    print(f"  files_updated: {summary['files_updated']}")
    print(f"  files_noop:    {summary['files_noop']}")
    print(f"  files_skipped: {summary['files_skipped']}")

    if summary.get("human_review_required"):
        print(f"  HUMAN_REVIEW_REQUIRED ({len(summary['human_review_required'])} files):")
        for p in summary["human_review_required"]:
            print(f"    {p}")

    for r in summary["results"]:
        status = r["result"]
        blocks = r.get("blocks_updated", 0)
        prose = r.get("prose_mentions", 0)
        path_short = Path(r["path"]).name
        if status not in (R_NOOP, R_SKIPPED_NO_BLOCK):
            detail = f"blocks={blocks}"
            if prose:
                detail += f" prose_mentions={prose}"
            if r.get("error"):
                detail += f" err={r['error']}"
            print(f"    {status}: {path_short} ({detail})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
