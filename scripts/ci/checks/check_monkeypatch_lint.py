# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_monkeypatch_lint.py — AST-first monkeypatch tier linter.

Enforces tiered monkeypatch policy:
  T1  Path constant patching       - BANNED
  T2  Internal function replacement - BANNED
  T3  External I/O boundary mocking - Requires annotation
  T4  Environment/dict patching     - Permitted

Detection uses ast module for .py files and regex for .md plan scanning.

Exit codes:
  0  - no violations (or warn-only mode)
  1  - violations found AND --strict is active
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# T1 guarded path constants (tiered monkeypatch policy)
# ---------------------------------------------------------------------------
GUARDED_NAMES: frozenset[str] = frozenset({
    "REPO_ROOT", "KNOWLEDGE_ROOT", "CONTENT_ROOT", "_SESSION_DIR",
    "_DEFAULT_CACHE", "_DEFAULT_REPO_ROOT", "_DEFAULT_KNOWLEDGE_ROOT",
    "_DEFAULT_CONTENT_ROOT", "_REPO_ROOT", "_DEFAULT_MANIFEST_PATH",
    "REPORTS_ROOT", "_ROOT", "_PENDING_DIR", "_ARCHIVED_DIR", "_RUNS_DIR",
    "CANONICAL_DIR", "_HERE",
})

# Known external/I/O modules whose attributes are T3 when mocked
_IO_MODULES: frozenset[str] = frozenset({
    "sys", "os", "subprocess", "requests", "urllib", "http", "socket",
    "shutil", "tempfile",
})

# Known I/O boundary targets (dotted or plain) -> T3
_IO_TARGETS: frozenset[str] = frozenset({
    "sys.argv", "sys.stdout", "sys.stderr", "sys.stdin",
    "subprocess.run", "subprocess.check_output", "subprocess.Popen",
    "os.environ", "os.path",
})


# ---------------------------------------------------------------------------
# Violation dataclass
# ---------------------------------------------------------------------------

class Violation:
    __slots__ = ("file", "line", "tier", "pattern", "target", "description")

    def __init__(self, file: str, line: int, tier: int, pattern: str,
                 target: str, description: str):
        self.file = file
        self.line = line
        self.tier = tier
        self.pattern = pattern
        self.target = target
        self.description = description

    def to_dict(self) -> dict:
        return {
            "file": self.file, "line": self.line, "tier": self.tier,
            "pattern": self.pattern, "target": self.target,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def classify_target(target_name: str) -> int:
    """Classify a mock target name into a tier (1-4)."""
    base = target_name.rsplit(".", 1)[-1] if "." in target_name else target_name
    if base in GUARDED_NAMES:
        return 1
    if target_name in _IO_TARGETS:
        return 3
    parts = target_name.split(".")
    if parts[0] in _IO_MODULES:
        return 3
    return 2


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------

def _get_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_attr_chain(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _get_attr_chain(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def _is_monkeypatch_setattr(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr == "setattr":
        chain = _get_attr_chain(node.func.value)
        if chain and "monkeypatch" in chain:
            return True
    return False


def _is_patch_object(node: ast.Call, patch_names: set[str]) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr == "object":
        chain = _get_attr_chain(node.func.value)
        if chain and chain in patch_names:
            return True
    return False


def _is_patch_call(node: ast.Call, patch_names: set[str]) -> bool:
    chain = _get_attr_chain(node.func)
    if chain and chain in patch_names:
        return True
    return False


def _is_patch_dict(node: ast.Call, patch_names: set[str]) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr == "dict":
        chain = _get_attr_chain(node.func.value)
        if chain and chain in patch_names:
            return True
    return False


def _extract_target_from_setattr(node: ast.Call) -> str | None:
    args = node.args
    if len(args) >= 2:
        name = _get_string_value(args[1])
        if name:
            return name
    if len(args) >= 1:
        s = _get_string_value(args[0])
        if s and "." in s:
            return s
    return None


def _extract_target_from_patch_object(node: ast.Call) -> str | None:
    args = node.args
    if len(args) >= 2:
        name = _get_string_value(args[1])
        if name:
            return name
    return None


def _extract_target_from_patch_call(node: ast.Call) -> str | None:
    args = node.args
    if len(args) >= 1:
        s = _get_string_value(args[0])
        if s:
            return s
    return None


def _find_patch_names(tree: ast.Module) -> set[str]:
    names: set[str] = {"patch"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "mock" in node.module:
                for alias in node.names:
                    if alias.name == "patch":
                        names.add(alias.asname or alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "mock" in alias.name:
                    names.add(alias.asname or alias.name)
    return names


def _has_t3_annotation(lines: list[str], lineno: int) -> bool:
    idx = lineno - 2
    if 0 <= idx < len(lines):
        return "# T3-MOCK:" in lines[idx]
    return False


def analyze_python_file(filepath: Path) -> list[Violation]:
    violations: list[Violation] = []
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return violations

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return violations

    patch_names = _find_patch_names(tree)
    rel_path = str(filepath)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        lineno = getattr(node, "lineno", 0)

        if _is_monkeypatch_setattr(node):
            target = _extract_target_from_setattr(node)
            if target:
                tier = classify_target(target)
                violations.append(Violation(
                    file=rel_path, line=lineno, tier=tier,
                    pattern="monkeypatch.setattr",
                    target=target,
                    description=f"T{tier}: monkeypatch.setattr on '{target}'",
                ))
            continue

        if _is_patch_dict(node, patch_names):
            violations.append(Violation(
                file=rel_path, line=lineno, tier=4,
                pattern="patch.dict",
                target="dict",
                description="T4: patch.dict (permitted)",
            ))
            continue

        if _is_patch_object(node, patch_names):
            target = _extract_target_from_patch_object(node)
            if target:
                tier = classify_target(target)
                violations.append(Violation(
                    file=rel_path, line=lineno, tier=tier,
                    pattern="patch.object",
                    target=target,
                    description=f"T{tier}: patch.object on '{target}'",
                ))
            continue

        if _is_patch_call(node, patch_names):
            target = _extract_target_from_patch_call(node)
            if target:
                tier = classify_target(target)
                violations.append(Violation(
                    file=rel_path, line=lineno, tier=tier,
                    pattern="patch",
                    target=target,
                    description=f"T{tier}: patch('{target}')",
                ))
            continue

    # Direct assignment: module.GUARDED_NAME = value
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr in GUARDED_NAMES:
                    violations.append(Violation(
                        file=rel_path, line=getattr(node, "lineno", 0),
                        tier=1, pattern="direct_assignment",
                        target=t.attr,
                        description=f"T1: direct assignment to '{t.attr}'",
                    ))

    return violations


# ---------------------------------------------------------------------------
# Backward-compatible check_file (returns list[tuple[int, str]])
# ---------------------------------------------------------------------------

def check_file(path: Path) -> list[tuple[int, str]]:
    """Legacy API: return (lineno, description) tuples for T1 violations only."""
    violations = analyze_python_file(path)
    result = []
    for v in violations:
        if v.tier == 1:
            if v.pattern == "monkeypatch.setattr":
                result.append((v.line, "monkeypatch.setattr on guarded path constant"))
            elif v.pattern == "patch.object":
                result.append((v.line, "patch.object on guarded path constant"))
            elif v.pattern == "patch":
                result.append((v.line, "patch() on guarded path constant"))
            elif v.pattern == "direct_assignment":
                result.append((v.line, "direct assignment to module path constant in test"))
            else:
                result.append((v.line, v.description))
    return result


# ---------------------------------------------------------------------------
# Plan/document scanning (regex-based for .md files)
# ---------------------------------------------------------------------------

_HISTORICAL_BLOCK = re.compile(
    r"<!--\s*HISTORICAL\s*-->.*?<!--\s*/HISTORICAL\s*-->",
    re.DOTALL,
)

_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)

_GUARDED_PAT = "|".join(sorted(GUARDED_NAMES))

_MD_T1_PATTERNS = [
    re.compile(r"monkeypatch\.setattr\s*\(.*?['\"](" + _GUARDED_PAT + r")['\"]"),
    re.compile(r"patch\.object\s*\(.*?['\"](" + _GUARDED_PAT + r")['\"]"),
    re.compile(r"@patch\s*\(\s*['\"][^'\"]*\.(" + _GUARDED_PAT + r")['\"]"),
]

_MD_T2_PATTERNS = [
    re.compile(r"monkeypatch\.setattr\s*\("),
    re.compile(r"patch\.object\s*\("),
    re.compile(r"@patch\s*\(\s*['\"]"),
]


def scan_md_file(filepath: Path, is_governance: bool = False) -> list[Violation]:
    violations: list[Violation] = []
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return violations

    cleaned = _HISTORICAL_BLOCK.sub("", text)
    if is_governance:
        cleaned = _FENCED_CODE.sub("", cleaned)

    rel_path = str(filepath)
    for lineno, line in enumerate(cleaned.splitlines(), 1):
        for pat in _MD_T1_PATTERNS:
            if pat.search(line):
                violations.append(Violation(
                    file=rel_path, line=lineno, tier=1,
                    pattern="md_recommendation",
                    target="T1 pattern in plan/doc",
                    description="T1 monkeypatch recommendation in plan/document",
                ))
                break
        else:
            for pat in _MD_T2_PATTERNS:
                if pat.search(line):
                    violations.append(Violation(
                        file=rel_path, line=lineno, tier=2,
                        pattern="md_recommendation",
                        target="T2 pattern in plan/doc",
                        description="T2 monkeypatch recommendation in plan/document",
                    ))
                    break

    return violations


# ---------------------------------------------------------------------------
# Baseline generation & comparison
# ---------------------------------------------------------------------------

def _collect_all_test_files(dirs: list[str] | None = None) -> list[Path]:
    if dirs is None:
        dirs = [
            "tests",
            "scripts/pipeline/tests",
            "scripts/translator/tests",
            "scripts/ci/tests",
        ]
    files: list[Path] = []
    for d in dirs:
        dp = Path(d)
        if dp.exists():
            for f in sorted(dp.rglob("test_*.py")):
                files.append(f)
    return files


def generate_baseline(test_dirs: list[str] | None = None) -> dict:
    files = _collect_all_test_files(test_dirs)
    totals = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    file_data: dict[str, dict[str, int]] = {}

    for f in files:
        violations = analyze_python_file(f)
        if not violations:
            continue
        counts = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
        for v in violations:
            key = f"T{v.tier}"
            counts[key] += 1
            totals[key] += 1
        rel = str(f).replace("\\", "/")
        file_data[rel] = counts

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/ci/checks/check_monkeypatch_lint.py --baseline",
        "generator_version": "2.0.0",
        "schema_version": 1,
        "totals": totals,
        "files": file_data,
    }


def compare_baseline(current: dict, committed_path: Path) -> list[str]:
    failures: list[str] = []
    try:
        committed = json.loads(committed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"Cannot read baseline at {committed_path}: {e}"]

    committed_totals = committed.get("totals", {})
    current_totals = current.get("totals", {})

    for tier in ["T1", "T2"]:
        cur = current_totals.get(tier, 0)
        base = committed_totals.get(tier, 0)
        if cur > base:
            failures.append(
                f"{tier} regression: {cur} > baseline {base} (+{cur - base})"
            )

    return failures


def check_ratchet(violations: list[Violation], ratchet_files: list[str]) -> list[str]:
    failures: list[str] = []
    ratchet_set = {f.replace("\\", "/") for f in ratchet_files}

    for rf in ratchet_set:
        file_violations = [v for v in violations if v.file.replace("\\", "/") == rf]
        t1_count = sum(1 for v in file_violations if v.tier == 1)
        if t1_count > 0:
            failures.append(f"Ratchet: {rf} has {t1_count} T1 violations (must be 0)")

    return failures


# ---------------------------------------------------------------------------
# Staged file helpers
# ---------------------------------------------------------------------------

def get_staged_test_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True,
        )
        paths = []
        for line in result.stdout.splitlines():
            p = Path(line.strip())
            if p.suffix == ".py" and ("test_" in p.name or p.name.startswith("test")):
                if p.exists():
                    paths.append(p)
        return paths
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AST-first monkeypatch tier linter ",
    )
    parser.add_argument("files", nargs="*", help="Test files to check")
    parser.add_argument("--staged", action="store_true",
                        help="Check only staged test files")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on violations (default: warn and exit 0)")
    parser.add_argument("--tier", type=str, default="1,2",
                        help="Comma-separated tiers to enforce (default: 1,2)")
    parser.add_argument("--baseline", action="store_true",
                        help="Generate baseline JSON to stdout")
    parser.add_argument("--compare-baseline", type=str, default=None,
                        metavar="PATH", help="Compare scan against committed baseline")
    parser.add_argument("--ratchet-files", type=str, default=None,
                        help="Comma-separated files for touched-file ratchet check")
    parser.add_argument("--all-files", action="store_true",
                        help="Scan all test files in standard directories")
    parser.add_argument("--require-annotation", action="store_true",
                        help="Require T3-MOCK annotation on T3 violations")
    parser.add_argument("--scan-plans", type=str, default=None,
                        metavar="DIR", help="Scan .md plan files for T1/T2 recommendations")
    parser.add_argument("--json", action="store_true",
                        help="Output violations as JSON")
    args = parser.parse_args(argv)

    enforced_tiers = {int(t.strip()) for t in args.tier.split(",")}

    if args.baseline:
        baseline = generate_baseline()
        print(json.dumps(baseline, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    # When ratchet or baseline comparison is requested without explicit files,
    # automatically scan all test files to ensure complete violation data.
    needs_all = bool(args.ratchet_files or args.compare_baseline)

    if args.all_files or (needs_all and not args.files and not args.staged):
        files = _collect_all_test_files()
    elif args.staged:
        files = get_staged_test_files()
    elif args.files:
        files = [Path(f) for f in args.files]
    else:
        parser.print_help()
        return 0

    all_violations: list[Violation] = []
    for fp in files:
        if fp.suffix == ".py":
            all_violations.extend(analyze_python_file(fp))

    if args.scan_plans:
        plan_dir = Path(args.scan_plans)
        if plan_dir.exists():
            for md in sorted(plan_dir.rglob("*.md")):
                if md.name == "CHANGELOG.md":
                    continue
                is_gov = md.name in ("AGENTS.md", "CONVENTIONS.md")
                all_violations.extend(scan_md_file(md, is_governance=is_gov))

    enforced_violations = [v for v in all_violations if v.tier in enforced_tiers]

    if args.require_annotation:
        for v in all_violations:
            if v.tier == 3:
                try:
                    lines = Path(v.file).read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                except OSError:
                    continue
                if not _has_t3_annotation(lines, v.line):
                    enforced_violations.append(Violation(
                        file=v.file, line=v.line, tier=3,
                        pattern="missing_t3_annotation",
                        target=v.target,
                        description=f"T3 mock without required T3-MOCK annotation: '{v.target}'",
                    ))

    baseline_failures: list[str] = []
    if args.compare_baseline:
        current_baseline = generate_baseline()
        baseline_failures = compare_baseline(
            current_baseline, Path(args.compare_baseline)
        )

    ratchet_failures: list[str] = []
    if args.ratchet_files:
        import re
        ratchet_list = [f.strip() for f in re.split(r"[,\s]+", args.ratchet_files) if f.strip()]
        ratchet_failures = check_ratchet(all_violations, ratchet_list)

    if args.json:
        output = {
            "violations": [v.to_dict() for v in enforced_violations],
            "baseline_failures": baseline_failures,
            "ratchet_failures": ratchet_failures,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        for v in enforced_violations:
            print(
                f"[monkeypatch-lint] {v.description} at {v.file}:{v.line}",
                file=sys.stderr,
            )

        for msg in baseline_failures:
            print(f"[monkeypatch-lint] BASELINE: {msg}", file=sys.stderr)

        for msg in ratchet_failures:
            print(f"[monkeypatch-lint] RATCHET: {msg}", file=sys.stderr)

    total_issues = len(enforced_violations) + len(baseline_failures) + len(ratchet_failures)

    if total_issues:
        # In ratchet/compare mode, only ratchet failures and baseline regressions
        # are blocking; existing violations are informational (WARN).
        blocking = len(baseline_failures) + len(ratchet_failures)
        if args.ratchet_files or args.compare_baseline:
            mode = "ERROR" if (args.strict and blocking) else "WARN"
        else:
            mode = "ERROR" if args.strict else "WARN"
        print(
            f"[monkeypatch-lint] {mode}: {total_issues} issue(s) in "
            f"{len(files)} file(s). See governance docs 16 for the tiered policy.",
            file=sys.stderr,
        )
        if mode == "ERROR":
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
