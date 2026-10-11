"""Tests for lib/example_verification/syntax.py (rollout step C2): the ONE
shared tree-sitter loader replacing the two independent, disagreeing copies
found by RC17 in smoke_test.py and code_syntax_check.py."""
from __future__ import annotations

from lib.example_verification.syntax import canonical_for, check_syntax, parser_for


def test_canonical_for_maps_aliases():
    assert canonical_for("c#") == "csharp"
    assert canonical_for("cs") == "csharp"
    assert canonical_for("C#") == "csharp"  # case-insensitive
    assert canonical_for("c++") == "cpp"
    assert canonical_for("ts") == "typescript"
    assert canonical_for("golang") == "go"
    assert canonical_for("py") == "python"


def test_canonical_for_unknown_lang_returns_none():
    assert canonical_for("mermaid") is None
    assert canonical_for("") is None
    assert canonical_for("cobol") is None


def test_check_syntax_unknown_lang_is_grammar_unavailable():
    result = check_syntax("cobol", "IDENTIFICATION DIVISION.")
    assert result.status == "GRAMMAR-UNAVAILABLE"
    assert result.proof_tier == 0


def test_check_syntax_valid_java_passes():
    code = "public class Foo {\n    public void bar() {}\n}\n"
    result = check_syntax("java", code)
    assert result.status == "PASS"
    assert result.proof_tier == 1


def test_check_syntax_invalid_java_fails():
    code = "public class Foo {\n    public void bar( {\n"
    result = check_syntax("java", code)
    assert result.status == "SYNTAX-ERROR"
    assert result.proof_tier == 1
    assert result.error_line is not None


def test_check_syntax_csharp_alias_tags_all_resolve():
    code = "class Foo {\n    void Bar() {}\n}\n"
    for tag in ("csharp", "cs", "c#"):
        result = check_syntax(tag, code)
        assert result.status == "PASS", f"{tag} unexpectedly failed: {result}"


def test_check_syntax_cpp_valid_passes():
    code = "int main() {\n    return 0;\n}\n"
    result = check_syntax("cpp", code)
    assert result.status == "PASS"


def test_check_syntax_typescript_valid_passes():
    code = "function add(a: number, b: number): number {\n  return a + b;\n}\n"
    result = check_syntax("typescript", code)
    assert result.status == "PASS"


def test_check_syntax_go_valid_passes():
    code = "package main\n\nfunc main() {\n\tprintln(\"hi\")\n}\n"
    result = check_syntax("go", code)
    assert result.status == "PASS"


def test_check_syntax_python_valid_passes():
    code = "def add(a, b):\n    return a + b\n"
    result = check_syntax("python", code)
    assert result.status == "PASS"


def test_check_syntax_rust_valid_passes():
    code = "fn main() {\n    println!(\"hi\");\n}\n"
    result = check_syntax("rust", code)
    assert result.status == "PASS"


def test_parser_for_is_cached_across_calls():
    p1 = parser_for("java")
    p2 = parser_for("java")
    assert p1 is p2


def test_check_syntax_missing_node_only_still_passes():
    # A partial/fragment snippet (e.g. reference-doc API shape) produces
    # only MISSING nodes, not a real ERROR node -- must still PASS.
    code = "public class Foo {\n    public void bar()"
    result = check_syntax("java", code)
    assert result.status == "PASS"


# ---------------------------------------------------------------------------
# TC-16 (MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION): shell-
# family languages, added 2026-09-24.
# ---------------------------------------------------------------------------

def test_canonical_for_shell_aliases_map_to_bash():
    assert canonical_for("bash") == "bash"
    assert canonical_for("sh") == "bash"
    assert canonical_for("shell") == "bash"


def test_canonical_for_powershell_aliases():
    assert canonical_for("powershell") == "powershell"
    assert canonical_for("ps1") == "powershell"


def test_canonical_for_bat_cmd_still_unmapped():
    """Deliberately NOT wired in -- the language pack's own "batch" grammar
    is unreliable (see syntax.py's own docstring)."""
    assert canonical_for("bat") is None
    assert canonical_for("cmd") is None


def test_check_syntax_valid_bash_passes():
    result = check_syntax("bash", "pip install aspose-pdf-foss\necho done")
    assert result.status == "PASS"
    assert result.proof_tier == 1


def test_check_syntax_invalid_bash_fails():
    code = "if [ true; then\n  echo missing fi"
    result = check_syntax("bash", code)
    assert result.status == "SYNTAX-ERROR"


def test_check_syntax_sh_and_shell_tags_resolve_via_bash_grammar():
    for tag in ("sh", "shell"):
        result = check_syntax(tag, "echo hello")
        assert result.status == "PASS", f"{tag} unexpectedly failed: {result}"


def test_check_syntax_valid_powershell_passes():
    code = '$x = 1\nif ($x -eq 1) { Write-Host "one" }'
    result = check_syntax("powershell", code)
    assert result.status == "PASS"


def test_check_syntax_invalid_powershell_fails():
    code = '$x = 1\nif ($x -eq 1 { Write-Host "broken" }'
    result = check_syntax("powershell", code)
    assert result.status == "SYNTAX-ERROR"


def test_check_syntax_cmd_still_grammar_unavailable():
    result = check_syntax("cmd", "echo hello")
    assert result.status == "GRAMMAR-UNAVAILABLE"
