"""check_professionalize_call_sites.py — CI gate: verify all professionalize call sites are registered.

Scans the repository for patterns that indicate professionalize transport calls
and verifies each matches an entry in the approved callsite registry. Unregistered
direct professionalize calls cause exit code 1.

Boundary systems (Gemini, Ollama, M2M) are excluded from professionalize scanning.
Test fixture files may be excluded or included via --include-tests.
Reports/metrics/ is excluded by default; use --include-reports to include.

Slice 9 of Agent Metrics Integration (METRICS-PLAN-001 v7.7).

Usage:
    python scripts/ci/checks/check_professionalize_call_sites.py
    python scripts/ci/checks/check_professionalize_call_sites.py --root /path/to/repo
    python scripts/ci/checks/check_professionalize_call_sites.py --registry path/to/registry.yaml
    python scripts/ci/checks/check_professionalize_call_sites.py --include-tests
    python scripts/ci/checks/check_professionalize_call_sites.py --include-reports
    python scripts/ci/checks/check_professionalize_call_sites.py --json-output

Exit codes:
    0  All detected professionalize call patterns are accounted for in the registry
    1  One or more unregistered direct professionalize calls detected
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_REGISTRY = _REPO_ROOT / "scripts" / "pipeline" / "config" / "metrics_callsite_registry.yaml"

# Patterns that suggest professionalize transport
_PROFESSIONALIZE_TRANSPORT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("llm.professionalize.com", re.compile(r"llm\.professionalize\.com", re.IGNORECASE)),
    ("GPT_OSS_ENDPOINT", re.compile(r"\bGPT_OSS_ENDPOINT\b")),
    ("GPT_OSS_API_KEY", re.compile(r"\bGPT_OSS_API_KEY\b")),
    ("PROFESSIONALIZE_API_KEY", re.compile(r"\bPROFESSIONALIZE_API_KEY\b")),
    ("LLM_API_BASE_URL", re.compile(r"\bLLM_API_BASE_URL\b")),
    ("LLM_API_KEY", re.compile(r"\bLLM_API_KEY\b")),
    ("LITELLM_KEY", re.compile(r"\bLITELLM_KEY\b")),
]

# Patterns that indicate active API client/transport usage (heavier signals)
_TRANSPORT_CODE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI(", re.compile(r"\bOpenAI\s*\(")),
    ("AsyncOpenAI(", re.compile(r"\bAsyncOpenAI\s*\(")),
    ("requests.post", re.compile(r"\brequests\.post\s*\(")),
    ("requests.Session", re.compile(r"\brequests\.Session\s*\(")),
    ("/chat/completions", re.compile(r"/chat/completions")),
    ("/embeddings", re.compile(r"/embeddings")),
    ("base_url=", re.compile(r"\bbase_url\s*=")),
]

# Directory names excluded no matter how deeply nested (vendored deps inside
# any worktree, submodule, or cache dir — these recur unpredictably, so they
# can't be defended by enumerating one more top-level entry each time a new
# worktree happens to contain one; see _is_excluded()).
_UNIVERSAL_NOISE_NAMES = {".venv", "venv", "__pycache__", ".git", "node_modules"}

# Files/dirs that are always excluded (boundary systems, generated files, etc.)
_ALWAYS_EXCLUDE_PATHS = {
    ".kilo",                                    # Git worktrees — copies of repo scripts, not our transport
    ".claude",                                  # Git worktrees — copies of repo scripts, not our transport
    "runs",                                     # Clone cache — FOSS code, not our transport
    "scripts/ci",                               # CI check scripts reference patterns as strings, not calls
    # Core metrics infrastructure — these ARE the approved transport layer, not new call sites
    "scripts/pipeline/commands/ops/professionalize_client.py",
    "scripts/pipeline/commands/ops/metrics_submitter.py",
    "scripts/pipeline/commands/ops/metrics_schema.py",
    "scripts/pipeline/commands/ops/metrics_event_ledger.py",
    "scripts/pipeline/commands/ops/metrics_payload_builder.py",
    "scripts/pipeline/commands/ops/run_metrics.py",
    "scripts/pipeline/config",                  # Config YAML files
    # Logical callers via LLMRouter (not direct transport call sites)
    "scripts/gap-eval",                         # Uses LLMRouter; CS-005/006/007 logical callers
    # Diagnostic/preflight tools (probes, not transport call sites)
    "scripts/translator/preflight",
    # Boundary systems
    "scripts/translator/backends/ollama.py",    # CS-012 Ollama boundary
    "scripts/translator/backends/m2m.py",       # CS-013 M2M boundary
    "scripts/seo/get_keywords.py",              # CS-010 Gemini boundary
    "scripts/seo/review_keywords.py",           # CS-011 Gemini boundary
}

# Strings that mark a line as a scanner fixture (exempt from scan)
_SCANNER_FIXTURE_MARKERS = [
    "# SCANNER_FIXTURE",
    "# scanner-fixture",
    "# metrics-scan-exempt",
]


@dataclass
class CallSiteMatch:
    file: str
    line: int
    pattern: str
    excerpt: str  # safe excerpt — no secret values


@dataclass
class RegistryEntry:
    call_site_id: str
    path: str
    capture_method: str
    allowed_capture_methods: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    registered_matches: list[CallSiteMatch] = field(default_factory=list)
    unregistered_matches: list[CallSiteMatch] = field(default_factory=list)
    registry_paths: list[str] = field(default_factory=list)
    registry_count: int = 0
    files_scanned: int = 0
    passed: bool = True
    governance_errors: list[str] = field(default_factory=list)


def _has_direct_transport(path: Path) -> bool:
    """Detect application-owned HTTP/SDK calls without matching string literals."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return False
    forbidden = {"urlopen", "OpenAI", "AsyncOpenAI"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in forbidden:
            return True
        if isinstance(func, ast.Attribute) and func.attr in {"post", "urlopen", "OpenAI", "AsyncOpenAI"}:
            return True
    return False


def _router_calls(path: Path) -> list[tuple[int, bool]]:
    """Return (line, has_context) for logical router calls."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"call_chat", "call_embeddings"}
        ):
            calls.append((
                node.lineno,
                any(keyword.arg == "context" for keyword in node.keywords),
            ))
    return calls


def _load_registry(registry_path: Path) -> tuple[list[RegistryEntry], list[str]]:
    """Load the callsite registry YAML. Returns (entries, registered_paths)."""
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        # Try without PyYAML using simple parse
        return _load_registry_simple(registry_path)

    if not registry_path.exists():
        return [], []

    with open(registry_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries: list[RegistryEntry] = []
    paths: list[str] = []
    call_sites = (data or {}).get("call_sites", {})
    for cs_id, cs_data in call_sites.items():
        cs_path = cs_data.get("path", "")
        capture_method = cs_data.get("capture_method", "")
        allowed = cs_data.get("allowed_capture_methods", [])
        entries.append(RegistryEntry(
            call_site_id=cs_id,
            path=cs_path,
            capture_method=capture_method,
            allowed_capture_methods=allowed if isinstance(allowed, list) else [allowed],
        ))
        if cs_path:
            # Normalize to forward slashes
            paths.append(cs_path.replace("\\", "/"))
    return entries, paths


def _load_registry_simple(registry_path: Path) -> tuple[list[RegistryEntry], list[str]]:
    """Fallback YAML parser for path extraction only."""
    if not registry_path.exists():
        return [], []
    entries = []
    paths = []
    current_id = None
    current_path = None
    current_method = None
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("CS-"):
            current_id = stripped.rstrip(":")
            current_path = None
            current_method = None
        if stripped.startswith("path:") and current_id:
            current_path = stripped.split(":", 1)[1].strip().strip('"')
        if stripped.startswith("capture_method:") and current_id:
            current_method = stripped.split(":", 1)[1].strip().strip('"')
        if current_id and current_path and current_method:
            entries.append(RegistryEntry(current_id, current_path, current_method))
            paths.append(current_path.replace("\\", "/"))
            current_id = None
            current_path = None
            current_method = None
    return entries, paths


def _is_excluded(rel_path: str, include_tests: bool, include_reports: bool) -> bool:
    """Return True if this path should be skipped."""
    forward = rel_path.replace("\\", "/")
    # Universal noise: excluded at ANY depth, not just at the repo root —
    # a vendored .venv/node_modules/etc. inside a nested worktree is just as
    # irrelevant as one at the top level.
    if any(p in _UNIVERSAL_NOISE_NAMES for p in forward.split("/")):
        return True
    # Always-excluded dirs/files (specific, repo-root-relative locations)
    for exc in _ALWAYS_EXCLUDE_PATHS:
        if forward == exc or forward.startswith(exc + "/"):
            return True
    # Reports dir
    if forward.startswith("reports/") and not include_reports:
        return True
    # Test files
    if not include_tests:
        parts = forward.split("/")
        if any(p in ("tests", "test") for p in parts):
            return True
        if any(p.startswith("test_") or p.endswith("_test.py") for p in parts):
            return True
    return False


def _safe_excerpt(line: str, max_len: int = 120) -> str:
    """Return a safe excerpt with potential secret values redacted."""
    # Redact token-like patterns before returning
    redacted = re.sub(
        r"(Bearer\s+)[A-Za-z0-9._-]{10,}",
        r"\1[REDACTED]",
        line.strip(),
    )
    redacted = re.sub(
        r"([?&](api_key|token|key)=)[^\s&]{8,}",
        r"\1[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted[:max_len]


def _is_scanner_fixture_line(line: str) -> bool:
    for marker in _SCANNER_FIXTURE_MARKERS:
        if marker in line:
            return True
    return False


def _is_comment_only(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("#") or stripped.startswith("//")


def _scan_file(
    file_path: Path,
    rel_path: str,
    registry_paths: list[str],
    patterns: list[tuple[str, re.Pattern[str]]],
) -> list[CallSiteMatch]:
    """Scan one file for professionalize patterns. Returns unregistered matches."""
    matches: list[CallSiteMatch] = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return matches

    # Track whether we're inside a triple-quoted docstring to skip documentation references
    in_docstring = False
    docstring_char = ""

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()

        # Docstring tracking (simplified: track """ and ''' toggling)
        if not in_docstring:
            # Check if this line opens a docstring
            for dq in ('"""', "'''"):
                count = stripped.count(dq)
                if count >= 2:
                    # Open and close on same line — not in docstring
                    break
                if count == 1:
                    in_docstring = True
                    docstring_char = dq
                    break
            if in_docstring:
                continue  # Skip this line (it's the opening of a docstring)
        else:
            # We're inside a docstring; check if it closes
            if docstring_char in stripped:
                in_docstring = False
            continue  # Skip all docstring lines

        # Skip comment-only lines
        if _is_comment_only(line):
            continue
        # Skip scanner fixture lines
        if _is_scanner_fixture_line(line):
            continue
        for pattern_name, pattern_re in patterns:
            if pattern_re.search(line):
                matches.append(CallSiteMatch(
                    file=rel_path,
                    line=lineno,
                    pattern=pattern_name,
                    excerpt=_safe_excerpt(line),
                ))
                break  # one match per line is enough
    return matches


def run_check(
    root: Path,
    registry_path: Path,
    include_tests: bool = False,
    include_reports: bool = False,
) -> CheckResult:
    result = CheckResult()
    entries, registry_paths = _load_registry(registry_path)
    result.registry_paths = registry_paths
    result.registry_count = len(registry_paths)

    canonical_transport_paths = {
        "scripts/pipeline/commands/ops/professionalize_client.py",
        # Router retains direct HTTP only for the local Ollama provider.
        "scripts/pipeline/commands/ops/llm_router.py",
    }
    for entry in entries:
        registered = root / entry.path
        if not entry.path or not registered.exists():
            result.governance_errors.append(
                f"{entry.call_site_id}: registered source path is missing: {entry.path}"
            )
            continue
        if entry.capture_method == "legacy_temporary":
            result.governance_errors.append(
                f"{entry.call_site_id}: legacy_temporary is prohibited"
            )
        normalized = entry.path.replace("\\", "/")
        if normalized not in canonical_transport_paths and _has_direct_transport(registered):
            result.governance_errors.append(
                f"{entry.call_site_id}: direct transport outside ProfessionalizeClient: {normalized}"
            )

    try:
        registry_text = registry_path.read_text(encoding="utf-8")
        if "legacy_temporary" in registry_text:
            result.governance_errors.append(
                "registry declares prohibited legacy_temporary metadata"
            )
        if 'api_key_source: "PROFESSIONALIZE_API_KEY' in registry_text:
            result.governance_errors.append(
                "registry credential metadata disagrees with llm_registry alias authority"
            )
    except OSError as exc:
        result.governance_errors.append(f"cannot read registry: {exc}")

    logical_paths: set[str] = set()
    try:
        import yaml  # type: ignore[import]
        registry_data = yaml.safe_load(registry_text) or {}
        call_sites_data = registry_data.get("call_sites", {}) or {}
        logical_paths = {
            item.get("path", "").replace("\\", "/")
            for item in registry_data.get("logical_consumers", [])
            if item.get("path")
        }
        for call_site_id, metadata in call_sites_data.items():
            if not isinstance(metadata, dict):
                result.governance_errors.append(
                    f"{call_site_id}: callsite metadata must be a mapping"
                )
                continue
            if metadata.get("capture_method") == "llm_router_native":
                if "LLMRouter" not in str(metadata.get("transport_type", "")):
                    result.governance_errors.append(
                        f"{call_site_id}: llm_router_native metadata disagrees with transport_type"
                    )
                metadata_text = " ".join(str(value) for value in metadata.values()).lower()
                if "direct urllib" in metadata_text:
                    result.governance_errors.append(
                        f"{call_site_id}: stale direct-transport metadata"
                    )

        summary = registry_data.get("summary")
        if isinstance(summary, dict):
            expected_counts = {
                "total_registered_transport_sites": len(call_sites_data),
                "active": sum(
                    1 for metadata in call_sites_data.values()
                    if isinstance(metadata, dict) and metadata.get("status") == "active"
                ),
                "wrapper_native": sum(
                    1 for metadata in call_sites_data.values()
                    if isinstance(metadata, dict)
                    and metadata.get("capture_method") == "wrapper_native"
                ),
                "llm_router_native": sum(
                    1 for metadata in call_sites_data.values()
                    if isinstance(metadata, dict)
                    and metadata.get("capture_method") == "llm_router_native"
                ),
                "approved_adapter": sum(
                    1 for metadata in call_sites_data.values()
                    if isinstance(metadata, dict)
                    and metadata.get("capture_method") == "approved_adapter"
                ),
            }
            for field, expected in expected_counts.items():
                if summary.get(field) != expected:
                    result.governance_errors.append(
                        f"registry summary {field}={summary.get(field)!r}, expected {expected}"
                    )
    except Exception as exc:
        result.governance_errors.append(f"cannot validate logical consumers: {exc}")

    for logical_path in logical_paths:
        if not (root / logical_path).exists():
            result.governance_errors.append(
                f"logical consumer source path is missing: {logical_path}"
            )

    # Combine transport + code patterns for scanning
    all_patterns = _PROFESSIONALIZE_TRANSPORT_PATTERNS + _TRANSPORT_CODE_PATTERNS

    for py_file in sorted(root.rglob("*.py")):
        try:
            rel = py_file.relative_to(root).as_posix()
        except ValueError:
            continue
        if _is_excluded(rel, include_tests=include_tests, include_reports=include_reports):
            continue
        result.files_scanned += 1
        norm_rel = rel.replace("\\", "/")
        is_registered = norm_rel in registry_paths

        if norm_rel != "scripts/pipeline/commands/ops/llm_router.py":
            for line, has_context in _router_calls(py_file):
                if norm_rel not in logical_paths:
                    result.governance_errors.append(
                        f"unregistered logical router consumer: {norm_rel}:{line}"
                    )
                elif not has_context:
                    result.governance_errors.append(
                        f"contextless router call: {norm_rel}:{line}"
                    )

        matches = _scan_file(py_file, rel, registry_paths, all_patterns)
        for m in matches:
            if is_registered:
                result.registered_matches.append(m)
            else:
                result.unregistered_matches.append(m)

    # Also scan YAML/config files for professionalize endpoint references
    # (only transport patterns, not code patterns)
    for yaml_file in sorted(root.rglob("*.yaml")):
        try:
            rel = yaml_file.relative_to(root).as_posix()
        except ValueError:
            continue
        if _is_excluded(rel, include_tests=include_tests, include_reports=include_reports):
            continue
        # Only scan transport patterns in YAML (not code patterns like OpenAI())
        matches = _scan_file(yaml_file, rel, registry_paths, _PROFESSIONALIZE_TRANSPORT_PATTERNS)
        for m in matches:
            if rel.replace("\\", "/") in registry_paths:
                result.registered_matches.append(m)
            else:
                # YAML config files referencing the endpoint are generally OK
                # (they are config, not executable call sites)
                # Only flag if they appear to be executable (e.g. not llm_registry.yaml/taxonomy)
                pass

    result.passed = (
        len(result.unregistered_matches) == 0
        and len(result.governance_errors) == 0
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify all professionalize call sites are registered in the callsite registry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=str(_REPO_ROOT), help="Repository root")
    parser.add_argument("--registry", default=str(_DEFAULT_REGISTRY), help="Registry YAML path")
    parser.add_argument("--include-tests", action="store_true", help="Include test files in scan")
    parser.add_argument("--include-reports", action="store_true", help="Include reports/ in scan")
    parser.add_argument("--json-output", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    root = Path(args.root)
    registry = Path(args.registry)

    result = run_check(
        root=root,
        registry_path=registry,
        include_tests=args.include_tests,
        include_reports=args.include_reports,
    )

    if args.json_output:
        print(json.dumps({
            "passed": result.passed,
            "registry_count": result.registry_count,
            "files_scanned": result.files_scanned,
            "registered_match_count": len(result.registered_matches),
            "unregistered_match_count": len(result.unregistered_matches),
            "unregistered": [
                {"file": m.file, "line": m.line, "pattern": m.pattern}
                for m in result.unregistered_matches
            ],
            "governance_errors": result.governance_errors,
        }, indent=2))
    else:
        print(f"check_professionalize_call_sites: scanned {result.files_scanned} files, "
              f"{result.registry_count} registered paths")
        if result.unregistered_matches or result.governance_errors:
            print(f"FAIL — {len(result.unregistered_matches)} unregistered professionalize pattern(s):")
            for m in result.unregistered_matches:
                print(f"  {m.file}:{m.line}  [{m.pattern}]  {m.excerpt}")
            for error in result.governance_errors:
                print(f"  GOVERNANCE: {error}")
        else:
            print(f"PASS — {len(result.registered_matches)} registered pattern(s) accounted for, "
                  "no unregistered direct calls detected")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
