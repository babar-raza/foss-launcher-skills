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
from content_discovery import english_counterpart_path  # noqa: E402

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

# TC-MT040-46: _VERSION_SPECIFIER_RE's character class ([<>=!~]) has no "@" in
# it, so it never strips npm's own trailing "@version" suffix (e.g.
# "@asposefoss/pdf@0.1.0") -- that token never normalized down to equal its
# own registered candidate.name ("@asposefoss/pdf"), a false mismatch.
# (?<=.) requires at least one character before the "@" being stripped, which
# excludes a leading bare "@" at token position 0 -- and even without that
# guard, a scoped package's leading "@" is always followed by a "/" before
# end-of-string, which [^@/]+$ (no "/" allowed in the stripped suffix) can
# never match through, so a version-less scoped name ("@asposefoss/pdf")
# survives unchanged either way. Order relative to the two strips above does
# not matter -- "@" never appears inside PEP 508 extras ("[...]", pip-only)
# or after a "<>=!~" version specifier (also pip-only); npm's "@version"
# shape and pip's "[extras]>=version" shape never co-occur in the same real
# token -- but it's applied last here, grouped with the final
# strip/lowercase normalization step.
_NPM_VERSION_SUFFIX_RE = re.compile(r"(?<=.)@[^@/]+$")


def _normalize_pkg_token(token: str) -> str:
    token = token.strip("'\"")
    token = _EXTRAS_RE.sub("", token)
    token = _VERSION_SPECIFIER_RE.sub("", token)
    token = _NPM_VERSION_SUFFIX_RE.sub("", token)
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

# RC-W1-003 (Mission MT026-2026-08-09-BLIND-SPOT-AUDIT-WAVE1, TC-BSA-...-03):
# _verify_install_accuracy (H-16) already loads data/package_registry.json
# for every page it checks, but only ever cross-references the package NAME
# field -- it never reads the neighboring verification.published boolean in
# the same loaded object. Confirmed live consequence: barcode/python's
# install/quickstart/getting-started pages (57 files across 5 subdomains)
# confidently claim the package "is published on PyPI" / link to a PyPI
# project page, while data/package_registry.json's
# barcode.python.verification.published is false. _CHANNEL_INFO maps each
# registry_type to the package-index channel a page might claim availability
# on (a prose mention of the channel's name, or a link into the channel's
# own domain) so _verify_publish_channel_claims can catch that contradiction
# directly -- reusing the same registry lookup shape _verify_install_accuracy
# already established, not inventing a new one.
# install_cmd_re reuses the exact same literal-command alternatives as
# _PKG_NAME_RE above, but applied to *prose* lines (backtick-quoted or
# plain), not just fenced code blocks -- the real barcode/python defect
# includes a prose sentence like "Add `pip install aspose-barcode-foss` to
# your CI pipeline's dependency step." which never appears inside a fenced
# ```bash block at all, so _verify_install_accuracy's block-scoped scan
# above would never see it.
_CHANNEL_INFO: dict[str, dict[str, Any]] = {
    "pypi": {
        "name": "PyPI",
        "domains": ("pypi.org",),
        "mention_re": re.compile(r"\bPyPI\b", re.IGNORECASE),
        "install_cmd_re": re.compile(r"pip\s+install\b", re.IGNORECASE),
    },
    "npm": {
        "name": "npm",
        "domains": ("npmjs.com", "npmjs.org"),
        "mention_re": re.compile(r"\bnpm(?:js)?\b", re.IGNORECASE),
        "install_cmd_re": re.compile(r"npm\s+install\b", re.IGNORECASE),
    },
    "nuget": {
        "name": "NuGet",
        "domains": ("nuget.org",),
        "mention_re": re.compile(r"\bNuGet\b", re.IGNORECASE),
        "install_cmd_re": re.compile(r"dotnet\s+add\s+package\b|nuget\s+install\b", re.IGNORECASE),
    },
    "cargo": {
        "name": "crates.io",
        "domains": ("crates.io",),
        "mention_re": re.compile(r"\bcrates\.io\b", re.IGNORECASE),
        "install_cmd_re": re.compile(r"cargo\s+add\b", re.IGNORECASE),
    },
    "maven": {
        "name": "Maven Central",
        "domains": ("repo1.maven.org", "search.maven.org", "mvnrepository.com", "central.sonatype.com"),
        "mention_re": re.compile(r"\bMaven\s+Central\b", re.IGNORECASE),
        "install_cmd_re": re.compile(r"<dependency\b|mvn\s+dependency", re.IGNORECASE),
    },
    "go_modules": {
        "name": "the Go module proxy",
        "domains": ("pkg.go.dev", "proxy.golang.org"),
        "mention_re": re.compile(r"\bpkg\.go\.dev\b", re.IGNORECASE),
        "install_cmd_re": re.compile(r"go\s+get\b", re.IGNORECASE),
    },
}

# Guard against flagging prose that already tells the truth (e.g. "not yet
# published on PyPI", "coming soon", "build from source") -- those are
# accurate, not a contradiction, even though they mention the channel name.
_NOT_PUBLISHED_NEGATION_RE = re.compile(
    r"not\s+(?:yet\s+)?(?:published|available)|coming\s+soon|build(?:ing)?\s+from\s+source",
    re.IGNORECASE,
)


def _has_unnegated_channel_claim(page: Page, channel: "dict[str, Any]") -> bool:
    """True if *page* has at least one channel mention/install-command/link
    not covered by _NOT_PUBLISHED_NEGATION_RE -- i.e. would itself trigger
    _verify_publish_channel_claims's FAIL. Factored out of that method (ST-214)
    so it can be run against an English counterpart page too, without
    duplicating the scan loop or its prev-line-wrap negation handling."""
    prev_line = ""
    for _line_no, line in page.prose_lines:
        if _NOT_PUBLISHED_NEGATION_RE.search(prev_line + " " + line):
            prev_line = line
            continue
        if channel["mention_re"].search(line) or channel["install_cmd_re"].search(line):
            return True
        prev_line = line
    for link in page.links:
        if _NOT_PUBLISHED_NEGATION_RE.search(link.text):
            continue
        url_lower = link.url.lower()
        if any(domain in url_lower for domain in channel["domains"]):
            return True
    return False

# ST-054 TC-14 (governing plan §Q.5): a public page must never disclose that a
# package isn't yet published (explicit operator policy, 2026-09-03/2026-09-10
# -- publication status is internal-only information). Deliberately NARROWER
# than _NOT_PUBLISHED_NEGATION_RE above, which also matches bare "build from
# source" -- that phrase is now the CORRECT answer a page should give (ST-054
# TC-13's shortcode fix renders exactly this), and must never trigger a FAIL
# here. Mirrors readme_refresh_checks.py's own already-proven
# _UNPUBLISHED_PACKAGE_SIGNAL_RE shape (a different pipeline/artifact -- FOSS
# README.md, not Hugo content -- but the same underlying disclosure phrases),
# rather than inventing a new pattern.
_UNPUBLISHED_DISCLOSURE_RE = re.compile(
    r"is\s+not\s+yet\s+published"
    r"|has\s+not\s+(?:yet\s+)?been\s+published"
    r"|has\s+not\s+yet\s+shipped"
    r"|coming\s+soon\b",
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
        # RC-W1-003: channel-availability prose claims ("published on PyPI",
        # a link to a PyPI/NuGet/npm/crates.io/Maven Central page) must be
        # cross-checked against verification.published the same way the
        # package-name check above cross-checks candidate.name -- and must
        # run unconditionally, same as accuracy_findings, so it still catches
        # _index.md and non-docs pages (the real barcode/python defect spans
        # getting-started/_index.md, which the docs-only/non-index gates
        # below would otherwise skip).
        accuracy_findings.extend(self._verify_publish_channel_claims(page))
        # ST-054 TC-14 (governing plan §Q.5): the opposite-direction check --
        # a page must never disclose non-publication status at all, not just
        # avoid falsely claiming publication. Runs unconditionally for the
        # same reason as the two checks above (must still catch _index.md
        # and non-docs pages).
        accuracy_findings.extend(self._verify_no_unpublished_disclosure(page))

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

    # ------------------------------------------------------------------
    # RC-W1-003: publish-channel availability claim verification
    # ------------------------------------------------------------------

    def _verify_publish_channel_claims(self, page: Page) -> list[Finding]:
        """Cross-check channel-availability prose claims ("published on
        PyPI", a link to the channel's own domain) against
        data/package_registry.json's verification.published boolean.

        Mirrors _verify_install_accuracy's registry lookup, but checks a
        different field of the same already-loaded entry: that check only
        ever compared candidate.name against install commands, and never
        read verification.published at all -- this is the fix for that gap
        (see module docstring / _CHANNEL_INFO comment for the RC-W1-003
        rationale and the confirmed barcode/python defect it closes)."""
        if not page.family or not page.platform:
            return []

        registry = _load_registry_cached()
        entry = registry.get(page.family, {}).get(page.platform)
        if not entry:
            return []

        verification = entry.get("verification") or {}
        if verification.get("published") is not False:
            # Only a *confirmed* published=false is a provable contradiction.
            # published=true, or an unresolved/missing verification
            # (None/absent), has nothing to contradict a claim with.
            return []

        channel = _CHANNEL_INFO.get(entry.get("registry_type"))
        if channel is None:
            return []

        # ST-214 (2026-09-24): _NOT_PUBLISHED_NEGATION_RE is an English-only
        # phrase regex (bare "not (yet) published"/"build from source" etc.)
        # -- structurally blind to a non-English translation of the exact
        # same, already-clean English sentence. Found live on 3d/typescript's
        # Arabic developer-guide/features.md: a faithful translation of the
        # accepted English "...installed automatically by the npm install
        # step used to build from source" triggered a bare-"npm" mention
        # match with no way for the negation regex to ever recognize the
        # Arabic negation context, regardless of what the sentence actually
        # says. Same mechanism already documented at ST-156. Fix: for a
        # non-English page, first check whether its English counterpart is
        # itself clean for this exact channel -- if so, trust the
        # translation (same "catch up to a clean English source" precedent
        # ST-153 already established for check_translation_regression.py's
        # R3 check) rather than scanning script-blind negation prose.
        if page.locale and page.locale != "en":
            eng_path = english_counterpart_path(page.filepath)
            if eng_path is not None and eng_path.is_file():
                eng_page = Page.load(eng_path)
                if not _has_unnegated_channel_claim(eng_page, channel):
                    return []

        verified_at = verification.get("verified_at") or "unknown date"
        findings: list[Finding] = []
        seen_lines: set[int] = set()

        def _emit(line_no: int, quoted: str) -> None:
            if line_no in seen_lines:
                return
            seen_lines.add(line_no)
            findings.append(Finding(
                level="FAIL",
                category="IR_PUBLISH_CLAIM",
                filepath=str(page.filepath),
                line_no=line_no,
                message=(
                    f"Page claims the package is published on {channel['name']} "
                    f"(\"{quoted.strip()}\"), but data/package_registry.json records "
                    f"{page.family}.{page.platform}.verification.published=false "
                    f"as of {verified_at}"
                ),
                suggestion=(
                    f"Remove or rewrite the {channel['name']} availability claim -- "
                    f"{page.family}/{page.platform} is not yet published (per "
                    "data/package_registry.json). Use the package-install shortcode "
                    "(or equivalent build-from-source guidance) instead of "
                    "hardcoding install/availability prose."
                ),
                evaluator=self.name,
            ))

        # The negation check must look one physical line back too: this
        # repo's generated markdown hard-wraps prose at a fixed width, so a
        # single logical sentence like "...is not yet\npublished on
        # crates.io):" routinely splits the negation word ("not yet") onto
        # the line BEFORE the channel-name mention. Checking only the
        # current physical line missed the negation and false-FAILed
        # already-honest "not yet published" prose. Found live 2026-09-03,
        # cells/rust's first install_recipe pass on its two launch blog
        # posts (both correctly say "the crate is not yet\npublished on
        # crates.io):", wrapped across exactly this line boundary).
        prev_line = ""
        for line_no, line in page.prose_lines:
            if _NOT_PUBLISHED_NEGATION_RE.search(prev_line + " " + line):
                prev_line = line
                continue
            if channel["mention_re"].search(line) or channel["install_cmd_re"].search(line):
                _emit(line_no, line)
            prev_line = line

        for link in page.links:
            if _NOT_PUBLISHED_NEGATION_RE.search(link.text):
                continue
            url_lower = link.url.lower()
            if any(domain in url_lower for domain in channel["domains"]):
                _emit(link.line_no, f"{link.text} -> {link.url}" if link.text else link.url)

        return findings

    def _verify_no_unpublished_disclosure(self, page: Page) -> list[Finding]:
        """ST-054 TC-14 (governing plan §Q.5): a public page must never
        disclose that a package isn't yet published -- explicit operator
        policy (2026-09-03, reinforced 2026-09-10): publication status is
        internal-only information, a public page must always show a real,
        working install command instead (ST-054 TC-13's shortcode fix now
        renders exactly that for every registered unpublished product).

        Shipped as WARN initially (ST-054 TC-14, 2026-09-10) while 46
        pre-existing files still carried this disclosure prose and needed
        individual review (ST-054 TC-16, not a scripted find/replace: each
        hit was a different shape -- frontmatter description, a table cell,
        body prose, blog narrative). Promoted to FAIL here as TC-16's own
        closing action, now that remediation has landed (commit f73e203027)
        and a full-corpus sweep confirms zero remaining instances --
        matching this repo's own established heuristic-then-hard-gate
        discipline for exactly this class of policy change (see
        readme_refresh_checks.py's check_installation_matches_package_registry
        -> check_installation_matches_live_publication, same discipline, a
        different pipeline/artifact)."""
        if not page.family or not page.platform:
            return []

        registry = _load_registry_cached()
        entry = registry.get(page.family, {}).get(page.platform)
        if not entry:
            return []

        verification = entry.get("verification") or {}
        if verification.get("published") is not False:
            # Only a confirmed published=false has anything to disclose;
            # published=true or unresolved (None/absent) is out of scope for
            # this specific check (mirrors _verify_publish_channel_claims's
            # own gate immediately above).
            return []

        findings: list[Finding] = []
        seen_lines: set[int] = set()
        for line_no, line in page.prose_lines:
            m = _UNPUBLISHED_DISCLOSURE_RE.search(line)
            if not m or line_no in seen_lines:
                continue
            seen_lines.add(line_no)
            findings.append(Finding(
                level="FAIL",
                category="IR_UNPUBLISHED_DISCLOSURE",
                filepath=str(page.filepath),
                line_no=line_no,
                message=(
                    f"Page discloses non-publication status ({m.group(0)!r}) for "
                    f"{page.family}/{page.platform} -- per 2026-09-10 policy, public "
                    "pages must show a real GitHub-source install path instead of "
                    "disclosing publish status"
                ),
                suggestion=(
                    "Remove the disclosure sentence. Use the package-install/"
                    "package-install-inline/maven-coord/maven-gav shortcode "
                    "(which now renders a real git-clone-based install command "
                    "for unpublished packages, ST-054 TC-13) or write the "
                    "equivalent from-source instructions directly, with zero "
                    "mention of publication status either way."
                ),
                evaluator=self.name,
            ))
        return findings
