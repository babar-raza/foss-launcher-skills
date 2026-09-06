"""
lib/example_verification/syntax.py

CONTRACT: scripts/pipeline/lib/example_verification/syntax.py
  purpose: the ONE tree-sitter grammar loader, replacing the two independent
           copies found by RC17 (`commands/diagnostics/smoke_test.py` and
           `content_eval/evaluators/code_syntax_check.py`), which disagree on
           which languages get a `tree_sitter_language_pack` fallback when
           the standalone wheel is absent -- confirmed live in this repo's
           own venv: smoke_test.py's copy resolves java/csharp/typescript/
           cpp/rust via the fallback, code_syntax_check.py's copy only
           resolves rust, so a Java page silently gets a WARN-only bracket
           heuristic in one subsystem and a real parse in the other. This
           module is both loaders merged, with fallback for every language
           either copy ever supported (java, csharp, typescript, javascript,
           cpp, rust, go, python).
  inputs:  a language tag (raw fence tag or canonical) + code text
  outputs: check_syntax() -> SyntaxCheckResult (PASS tier 1 | SYNTAX-ERROR |
           GRAMMAR-UNAVAILABLE)
  owner_domain: content-quality

GRAMMAR-UNAVAILABLE is loud by design (Round 3 A / Phase 0 item 9): the
smoke_test.py copy this replaces silently reported PASS when no parser was
available (`smoke_test.py:424-434`, pre-fix) -- a missing grammar and a
genuinely clean parse must never look the same to a caller deciding whether
a block has real proof behind it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Canonical lang -> the handful of raw fence-tag spellings that mean it.
# Kept independent of code_fences.canonicalize_lang() (zero-dependency
# module, per this module's own docstring) but intentionally the same
# mapping shape.
_CANONICAL_TAGS: dict[str, tuple[str, ...]] = {
    "java": ("java",),
    "csharp": ("csharp", "cs", "c#"),
    "typescript": ("typescript", "ts"),
    "javascript": ("javascript", "js"),
    "cpp": ("cpp", "c++"),
    "rust": ("rust", "rs"),
    "go": ("go", "golang"),
    "python": ("python", "py"),
}

# language_pack's own canonical name for each entry above (differs from our
# canonical key only for csharp -> "c_sharp").
_LANGUAGE_PACK_NAME: dict[str, str] = {
    "java": "java",
    "csharp": "c_sharp",
    "typescript": "typescript",
    "javascript": "javascript",
    "cpp": "cpp",
    "rust": "rust",
    "go": "go",
    "python": "python",
}

_TAG_TO_CANONICAL: dict[str, str] = {
    tag: canonical for canonical, tags in _CANONICAL_TAGS.items() for tag in tags
}

_PARSER_CACHE: dict[str, Any] = {}
_ATTEMPTED: set[str] = set()


def canonical_for(lang_tag: str) -> str | None:
    """Map a raw fence tag to the canonical key this loader indexes parsers
    by, or None if the tag isn't a language this loader knows about."""
    return _TAG_TO_CANONICAL.get((lang_tag or "").strip().lower())


def _load_standalone_wheel(canonical: str) -> Any | None:
    """Try the standalone `tree-sitter-<lang>` wheel for one canonical
    language. Returns a ready Parser, or None if the wheel isn't installed
    or fails to build (never raises)."""
    try:
        from tree_sitter import Language, Parser  # type: ignore[import]
    except ImportError:
        return None

    try:
        if canonical == "java":
            import tree_sitter_java as mod
            return Parser(Language(mod.language()))
        if canonical == "csharp":
            import tree_sitter_c_sharp as mod
            return Parser(Language(mod.language()))
        if canonical == "typescript":
            import tree_sitter_typescript as mod
            return Parser(Language(mod.language_typescript()))
        if canonical == "javascript":
            import tree_sitter_javascript as mod
            return Parser(Language(mod.language()))
        if canonical == "cpp":
            import tree_sitter_cpp as mod
            return Parser(Language(mod.language()))
        if canonical == "rust":
            import tree_sitter_rust as mod
            return Parser(Language(mod.language()))
        if canonical == "go":
            import tree_sitter_go as mod
            return Parser(Language(mod.language()))
        if canonical == "python":
            import tree_sitter_python as mod
            return Parser(Language(mod.language()))
    except Exception:
        return None
    return None


def _load_language_pack(canonical: str) -> Any | None:
    """Fall back to `tree_sitter_language_pack.get_parser`, which bundles
    grammars for languages that don't ship (or aren't installed as) a
    standalone wheel in this repo's venv. Never raises."""
    try:
        from tree_sitter_language_pack import get_parser  # type: ignore[import]
    except Exception:
        return None
    try:
        return get_parser(_LANGUAGE_PACK_NAME[canonical])
    except Exception:
        return None


def parser_for(lang_tag: str) -> Any | None:
    """Return a cached tree-sitter Parser for `lang_tag` (any spelling in
    _CANONICAL_TAGS), trying the standalone wheel first and the language
    pack second. Returns None (only) if neither source can produce a
    parser, or if `lang_tag` isn't a language this loader knows about.
    Result is cached per canonical language for the life of the process."""
    canonical = canonical_for(lang_tag)
    if canonical is None:
        return None
    if canonical in _PARSER_CACHE:
        return _PARSER_CACHE[canonical]
    if canonical in _ATTEMPTED:
        return None
    _ATTEMPTED.add(canonical)

    parser = _load_standalone_wheel(canonical) or _load_language_pack(canonical)
    if parser is not None:
        _PARSER_CACHE[canonical] = parser
    return parser


def _first_error_node(node: Any) -> Any | None:
    """Return the first ERROR node in the tree (BFS), or None. MISSING
    nodes (parser-inserted tokens completing a partial parse) are normal in
    snippet-shaped code and are never treated as errors."""
    queue = [node]
    while queue:
        n = queue.pop(0)
        if n.type == "ERROR":
            return n
        queue.extend(n.children)
    return None


@dataclass(frozen=True, slots=True)
class SyntaxCheckResult:
    status: str          # "PASS" | "SYNTAX-ERROR" | "GRAMMAR-UNAVAILABLE"
    proof_tier: int       # 1 on PASS/SYNTAX-ERROR (a real parse ran), 0 on GRAMMAR-UNAVAILABLE
    message: str = ""
    error_line: int | None = None


def check_syntax(lang_tag: str, code: str) -> SyntaxCheckResult:
    """Tier-1 syntax proof for one code block: a real tree-sitter parse.

    PASS (proof_tier=1): parsed with no genuine ERROR node.
    SYNTAX-ERROR (proof_tier=1): a real ERROR node was found -- a tree-sitter
      parse DID run, so this is still tier-1 proof, just a negative result.
    GRAMMAR-UNAVAILABLE (proof_tier=0): no parser could be loaded for this
      language on this machine -- loud by design (see module docstring);
      never silently reported as PASS.
    """
    parser = parser_for(lang_tag)
    if parser is None:
        return SyntaxCheckResult(
            status="GRAMMAR-UNAVAILABLE", proof_tier=0,
            message=f"no tree-sitter grammar available for '{lang_tag}'",
        )

    try:
        tree = parser.parse(code.encode("utf-8", errors="replace"))
    except Exception as exc:  # never let a parser crash the caller
        return SyntaxCheckResult(
            status="GRAMMAR-UNAVAILABLE", proof_tier=0,
            message=f"parser raised for '{lang_tag}': {exc}",
        )

    if not tree.root_node.has_error:
        return SyntaxCheckResult(status="PASS", proof_tier=1)

    error_node = _first_error_node(tree.root_node)
    if error_node is None:
        # Only MISSING nodes -- a parser-inserted completion, not a real
        # error in a snippet that's intentionally a fragment.
        return SyntaxCheckResult(status="PASS", proof_tier=1)

    line_no = error_node.start_point[0] + 1
    return SyntaxCheckResult(
        status="SYNTAX-ERROR", proof_tier=1,
        message=f"syntax error at line {line_no} (tree-sitter)",
        error_line=line_no,
    )
