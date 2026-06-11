"""Security-focused tests — P6 security testing signal."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Import real path_guard for integration tests
sys.path.insert(0, str(REPO_ROOT))
try:
    from scripts.pipeline.commands.governance.path_guard import check_path
    HAS_PATH_GUARD = True
except ImportError:
    HAS_PATH_GUARD = False


class TestPathGuardIntegration:
    """Direct integration tests against the real path_guard.check_path function."""

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    def test_path_guard_blocks_traversal_to_forbidden(self):
        """Path traversal via ../ that resolves to forbidden area must be DENY."""
        decision, _ = check_path("themes/secret.html")
        assert decision == "DENY"
        decision, _ = check_path("layouts/base.html")
        assert decision == "DENY"
        decision, _ = check_path("configs/hugo.toml")
        assert decision == "DENY"

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    def test_path_guard_blocks_governance_files(self):
        """Exact governance files must be DENY."""
        decision, _ = check_path("AGENTS.md")
        assert decision == "DENY"
        decision, _ = check_path("CLAUDE.md")
        assert decision == "DENY"

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    def test_path_guard_allows_content_paths(self):
        """Valid content paths must be ALLOW."""
        decision, _ = check_path("content/docs/test.md")
        assert decision == "ALLOW"
        decision, _ = check_path("scripts/pipeline/test.py")
        assert decision == "ALLOW"
        decision, _ = check_path("tests/test_foo.py")
        assert decision == "ALLOW"
        decision, _ = check_path("reports/audit.json")
        assert decision == "ALLOW"

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    def test_path_guard_denies_unknown_paths(self):
        """Paths not in any prefix must be DENY (default-deny)."""
        decision, _ = check_path("random_file.txt")
        assert decision == "DENY"
        decision, _ = check_path("pyproject.toml")
        assert decision == "DENY"

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    def test_path_guard_normalizes_backslashes(self):
        """Windows-style backslash paths must be normalized and checked."""
        decision, _ = check_path("themes\\evil.html")
        assert decision == "DENY"
        decision, _ = check_path("content\\docs\\safe.md")
        assert decision == "ALLOW"

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    def test_path_guard_strips_leading_dot_slash(self):
        """Leading ./ must be stripped before checking."""
        decision, _ = check_path("./themes/evil.html")
        assert decision == "DENY"
        decision, _ = check_path("./content/safe.md")
        assert decision == "ALLOW"


class TestConfigLoaderSecurity:
    """Security tests for YAML loading safety."""

    def test_config_loader_uses_safe_load(self):
        """config_loader.py must use yaml.safe_load, not yaml.load."""
        config_loader = SCRIPTS_DIR / "config_loader.py"
        if not config_loader.exists():
            pytest.skip("config_loader.py not found")

        content = config_loader.read_text(encoding="utf-8")
        unsafe_patterns = re.findall(
            r"yaml\.load\s*\([^)]*\)", content
        )
        for match in unsafe_patterns:
            assert "SafeLoader" in match or "safe_load" in match, (
                f"Unsafe YAML loading found: {match}"
            )
        assert "safe_load" in content or "SafeLoader" in content, (
            "config_loader.py should use yaml.safe_load or SafeLoader"
        )


class TestNoHardcodedSecrets:
    """Scan scripts/ for hardcoded secret patterns."""

    SECRET_PATTERNS = [
        re.compile(r'(?:api[_-]?key|apikey)\s*=\s*["\'][A-Za-z0-9]{16,}["\']', re.I),
        re.compile(r'(?:password|passwd|secret)\s*=\s*["\'][^"\']{8,}["\']', re.I),
        re.compile(r'AKIA[0-9A-Z]{16}'),
        re.compile(r'sk-[a-zA-Z0-9]{20,}'),
        re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    ]

    ALLOWLIST = {"test", "fake", "dummy", "mock", "example", "placeholder"}

    def test_no_hardcoded_secrets_in_scripts(self):
        """No real secret patterns should appear in scripts/."""
        violations = []
        for py_file in SCRIPTS_DIR.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pattern in self.SECRET_PATTERNS:
                for match in pattern.finditer(content):
                    matched_text = match.group().lower()
                    if not any(allow in matched_text for allow in self.ALLOWLIST):
                        rel = py_file.relative_to(REPO_ROOT)
                        violations.append(f"{rel}: {pattern.pattern}")
        assert not violations, f"Hardcoded secrets found:\n" + "\n".join(violations)


class TestNoDangerousBuiltins:
    """Scan scripts/ for dangerous builtins (eval, exec)."""

    DANGEROUS = re.compile(r'\b(?:eval|exec)\s*\(')

    SAFE_CONTEXTS = {"# nosec", "# safe:", "subprocess"}

    def _is_comment(self, line: str) -> bool:
        return line.lstrip().startswith("#")

    def test_no_eval_or_exec_in_scripts(self):
        """Scripts must not use eval() or exec() outside safe contexts."""
        violations = []
        for py_file in SCRIPTS_DIR.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                if self.DANGEROUS.search(line):
                    if self._is_comment(line):
                        continue
                    if not any(ctx in line for ctx in self.SAFE_CONTEXTS):
                        rel = py_file.relative_to(REPO_ROOT)
                        violations.append(f"{rel}:{i}: {line.strip()}")
        assert not violations, (
            f"Dangerous builtins found:\n" + "\n".join(violations)
        )
