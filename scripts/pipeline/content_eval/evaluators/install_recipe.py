"""Install recipe evaluator — detects API documentation pages that lack installation guidance.

Documentation pages that demonstrate API usage (code blocks or backtick
references) but contain no installation instructions and no link to an
installation page are flagged as INFO.  This is a cross-page concern, so the
severity is kept low.

H-16 (``_verify_install_accuracy``) is a second, independent check: it
cross-checks install commands actually present in a page's code blocks.
Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE (TC-MT018-07) found this
had the identical blind spot as audit/package_install_literal.py -- it
silently returned ``[]`` whenever knowledge/{family}/{platform}/merged/
install.md didn't exist, which is most products (that file is a vestigial,
rarely-populated hand-written stub). Fixed by making
data/package_registry.json -- not install.md -- the primary ground truth:

1. A family/platform with NO registry entry at all is now a FAIL the moment
   any install-command-shaped line appears in a relevant code block (mirrors
   package_install_literal.py's fix; this evaluator feeds a different gate,
   no_downgrade_guard.py via content_eval, so needed the same fix
   independently -- fixing one does not fix the other).
2. A registered family/platform's install commands are cross-checked against
   the registry's verified candidate name (install.md, when present, still
   supplements this as an additional accepted name).
3. The wrong-platform-package-manager check (e.g. `pip install` on a .NET
   page) is now unconditional -- previously it was gated behind the same
   install.md-exists check as the accuracy comparison, even though it has no
   actual dependency on install.md's content at all.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# sibling-import guard: content_eval sub-package needs the pipeline root +
# lib/ for package_registry_data (mirrors api_accuracy.py's established
# pattern for reaching audit-layer/lib machinery from content_eval).
_HERE = Path(__file__).resolve().parent.parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from package_registry_data import load_registry  # noqa: E402

_DEFAULT_KNOWLEDGE_ROOT = Path("knowledge")
KNOWLEDGE_ROOT = _DEFAULT_KNOWLEDGE_ROOT
_REGISTRY_OVERRIDE: "dict | None" = None


def configure(*, knowledge_root: "Path | str | None" = None, registry: "dict | None" = None) -> None:
    """Override the module-level KNOWLEDGE_ROOT / registry for testing.

    Mirrors content_discovery.py's configure() seam (AGENTS.md 16) -- the
    sanctioned alternative to monkeypatching KNOWLEDGE_ROOT directly, which
    is a T1-banned guarded-path-constant patch. ``registry`` (added
    TC-MT018-07) overrides data/package_registry.json the same way --
    without it, tests would silently depend on the real repo file's live
    contents, which drift over time independent of any code change.
    """
    global KNOWLEDGE_ROOT, _REGISTRY_OVERRIDE
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT
    _REGISTRY_OVERRIDE = registry


def _load_registry_cached() -> dict:
    return _REGISTRY_OVERRIDE if _REGISTRY_OVERRIDE is not None else load_registry()

# Package-manager / install command patterns (case-insensitive)
_INSTALL_PROSE_RE = re.compile(
    r"pip\s+install|mvn\b|<dependency\b|dotnet\s+add\s+package|nuget\b"
    r"|npm\s+install|cargo\s+add|\[dependencies\]|gem\s+install"
    r"|composer\s+require",
    re.IGNORECASE,
)

# Heading text patterns that indicate an install/setup section
_INSTALL_HEADING_RE = re.compile(
    r"\b(?:install|setup|prerequisite|requirement|getting[\s-]started)\b",
    re.IGNORECASE,
)

# URL fragments that suggest a link to an install page
_INSTALL_URL_RE = re.compile(
    r"installation|getting-started|getting_started|quickstart",
    re.IGNORECASE,
)

# Slug patterns: if the page itself is an install/setup page, skip it
_INSTALL_SLUG_RE = re.compile(
    r"installation|getting-started|getting_started|install\b|setup",
    re.IGNORECASE,
)

# Backtick API reference pattern in prose
_BACKTICK_API_RE = re.compile(r"`[A-Z][A-Za-z0-9]+(?:\.[a-zA-Z0-9]+)?`")

# H-16: Package name extraction from install commands. Skips leading CLI
# flags (`--upgrade`, `-e`, `-r`, ...) so the captured group is the actual
# package token, not a flag -- found live (2026-08-01, TC-MT018-07 sweep)
# via `pip install --upgrade aspose-words-foss` matching `--upgrade` as the
# "package name".
_PKG_NAME_RE = re.compile(
    r"(?:pip\s+install|npm\s+install|dotnet\s+add\s+package|nuget\s+install"
    r"|cargo\s+add)(?:\s+-{1,2}\S+)*\s+(\S+)",
    re.IGNORECASE,
)

# H-16: strip PEP 508 extras (`[pdf]`) and version specifiers (`>=26.4.0`)
# from a captured package token before comparing against a known name --
# found live (2026-08-01, TC-MT018-07 sweep): version-pinned/extras-qualified
# commands like `pip install "aspose-note[pdf]>=26.3.2"` were mismatching
# their own correct, registered package name token-for-token.
_VERSION_SPECIFIER_RE = re.compile(r"[<>=!~].*$")
_EXTRAS_RE = re.compile(r"\[[^\]]*\]")


def _normalize_pkg_token(token: str) -> str:
    token = token.strip("'\"")
    token = _EXTRAS_RE.sub("", token)
    token = _VERSION_SPECIFIER_RE.sub("", token)
    return token.strip().lower()

# H-16: Platform → expected package managers
_PLATFORM_PKG_MANAGERS: dict[str, set[str]] = {
    "python": {"pip"},
    "net": {"dotnet", "nuget"},
    "java": {"mvn", "gradle"},
    "cpp": {"vcpkg", "conan", "cmake"},
    "typescript": {"npm", "yarn", "pnpm"},
    "javascript": {"npm", "yarn", "pnpm"},
    "rust": {"cargo"},
}

# Package manager detection pattern
_PKG_MANAGER_RE = re.compile(
    r"\b(pip|npm|yarn|pnpm|dotnet|nuget|mvn|gradle|vcpkg|conan|cmake|cargo|gem|composer)\b",
    re.IGNORECASE,
)


class InstallRecipeEvaluator(BaseEvaluator):
    """Flags documentation pages that demonstrate API usage but lack install guidance,
    and cross-checks install-command accuracy (H-16) against knowledge.

    The "missing install instructions" INFO suggestion only applies to ``docs``
    subdomain pages with role ``docs``/``howto`` that are not index pages --
    installation instructions may legitimately live on a linked page there.
    H-16's accuracy check (ST-047) runs on every subdomain (docs/kb/blog/
    products): a wrong package name or wrong-platform package manager is a
    defect wherever it appears, not just in docs.
    """

    name = "install_recipe"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # ST-047 fix: H-16 (install-command accuracy) must run across every
        # subdomain, not just docs. It previously sat behind the docs-only
        # gate below, so content_eval had zero visibility into kb/blog/
        # products pages -- confirmed by the 3D-NET-REFRESH-002 remediation,
        # where 19 wrong-NuGet-command files spanned all 4 content surfaces
        # but the evaluator only ever checked docs.aspose.org. Runs first,
        # unconditionally; the docs-only gate below now only scopes the
        # separate "missing install instructions" suggestion.
        accuracy_findings = self._verify_install_accuracy(page)

        # Gate: the "missing install instructions" suggestion legitimately
        # only applies to docs subdomain pages with role docs/howto
        # (non-index) -- kb/blog/products pages aren't expected to carry a
        # full install section, so that narrower check stays scoped as
        # before.
        if page.subdomain != "docs":
            return accuracy_findings
        if page.page_role not in ("docs", "howto"):
            return accuracy_findings
        if page.filepath.name == "_index.md":
            return accuracy_findings

        # Skip if this page IS an installation/setup page
        page_path_str = str(page.filepath).replace("\\", "/")
        if _INSTALL_SLUG_RE.search(page_path_str):
            return accuracy_findings

        # Check whether the page has meaningful API usage
        code_block_count = len(page.code_blocks)
        backtick_api_count = sum(
            len(_BACKTICK_API_RE.findall(line))
            for _, line in page.prose_lines
        )
        has_api_usage = code_block_count >= 1 or backtick_api_count >= 3
        if not has_api_usage:
            return accuracy_findings

        # Check for installation content in prose
        for _, line in page.prose_lines:
            if _INSTALL_PROSE_RE.search(line):
                return accuracy_findings  # Install instructions present

        # Check for install instructions inside code blocks
        for block in page.code_blocks:
            if _INSTALL_PROSE_RE.search(block.content):
                return accuracy_findings

        # Check for install-related headings
        for heading in page.headings:
            if _INSTALL_HEADING_RE.search(heading.text):
                return accuracy_findings

        # Check for links pointing to an installation page
        for link in page.links:
            if _INSTALL_URL_RE.search(link.url):
                return accuracy_findings

        # No install content found — build a helpful suggestion
        suggestion = (
            "Add installation instructions or link to an installation page. "
        )
        if page.family and page.platform:
            install_md = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "install.md"
            if install_md.exists():
                content = install_md.read_text(encoding="utf-8", errors="replace")
                if len(content) > 50:
                    suggestion += (
                        f"Installation content is available at "
                        f"knowledge/{page.family}/{page.platform}/merged/install.md"
                    )

        accuracy_findings.append(Finding(
            level="INFO",
            category="IR",
            filepath=str(page.filepath),
            line_no=1,
            message=(
                f"Page demonstrates API usage ({code_block_count} code block(s), "
                f"{backtick_api_count} backtick ref(s)) but has no installation instructions"
            ),
            suggestion=suggestion.strip(),
            evaluator=self.name,
        ))
        return accuracy_findings

    # ------------------------------------------------------------------
    # H-16: Install accuracy verification
    # ------------------------------------------------------------------

    def _verify_install_accuracy(self, page: Page) -> list[Finding]:
        """Cross-check install commands against data/package_registry.json
        (primary) and knowledge/merged/install.md (supplementary); flag
        wrong-platform package managers unconditionally. See module docstring
        for the TC-MT018-07 rationale."""
        if not page.family or not page.platform:
            return []

        registry = _load_registry_cached()
        entry = registry.get(page.family, {}).get(page.platform)

        known_packages: set[str] = set()
        if entry:
            candidate = entry.get("candidate") or {}
            candidate_name = candidate.get("name") or candidate.get("module_path")
            if candidate_name:
                known_packages.add(_normalize_pkg_token(candidate_name))

        install_md = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "install.md"
        if install_md.exists():
            try:
                knowledge_text = install_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                knowledge_text = ""
            if len(knowledge_text) >= 20:
                known_packages.update(
                    _normalize_pkg_token(m.group(1)) for m in _PKG_NAME_RE.finditer(knowledge_text)
                )

        findings: list[Finding] = []
        expected_managers = _PLATFORM_PKG_MANAGERS.get(page.platform, set())

        for block in page.code_blocks:
            if block.lang not in ("bash", "shell", "sh", "powershell", "cmd",
                                  "console", "text", "plain", ""):
                continue

            page_packages = set(
                _normalize_pkg_token(m.group(1)) for m in _PKG_NAME_RE.finditer(block.content)
            )
            page_packages.discard("")

            if entry is None:
                if page_packages:
                    findings.append(Finding(
                        level="FAIL",
                        category="IR",
                        filepath=str(page.filepath),
                        line_no=block.start_line,
                        message=(
                            "Install command found for an UNREGISTERED "
                            f"family/platform: {page.family}/{page.platform}"
                        ),
                        suggestion=(
                            f"{page.family}/{page.platform} has no entry in "
                            "data/package_registry.json -- there is no live-verified "
                            "identity to ground this command against. Add a registry "
                            "entry first (registry_backfill.py), then use the "
                            "appropriate package-install shortcode. See Mission "
                            "MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE."
                        ),
                        evaluator=self.name,
                    ))
            elif known_packages:
                for pkg in page_packages:
                    if pkg not in known_packages:
                        findings.append(Finding(
                            level="WARN",
                            category="IR",
                            filepath=str(page.filepath),
                            line_no=block.start_line,
                            message=(
                                f"Install command references `{pkg}` but the "
                                f"verified identity for {page.family}/{page.platform} "
                                "is different"
                            ),
                            suggestion=(
                                "Verify package name against "
                                "data/package_registry.json (and "
                                f"knowledge/{page.family}/{page.platform}/merged/install.md "
                                "if present)"
                            ),
                            evaluator=self.name,
                        ))

            # Wrong-platform package manager check -- unconditional, no
            # dependency on install.md or registry state at all: this is a
            # self-contained structural check (does an inappropriate package
            # manager appear on this platform's page).
            if expected_managers:
                for m in _PKG_MANAGER_RE.finditer(block.content):
                    manager = m.group(1).lower()
                    if manager not in expected_managers:
                        findings.append(Finding(
                            level="WARN",
                            category="IR",
                            filepath=str(page.filepath),
                            line_no=block.start_line + block.content[:m.start()].count("\n"),
                            message=(
                                f"Package manager `{manager}` is not appropriate "
                                f"for {page.platform} platform"
                            ),
                            suggestion=(
                                f"Use {', '.join(sorted(expected_managers))} "
                                f"instead of `{manager}` for {page.platform}"
                            ),
                            evaluator=self.name,
                        ))

        return findings
