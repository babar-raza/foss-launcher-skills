"""Regression test for TC-02/G-02 (MT009 SEED-20): extract_claims() must not
double-fire on Python 'from X import Y' statements, tagging the imported
class/function Y itself as a package-declaration claim.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow imports from scripts/gap-eval/src/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from run import extract_claims  # type: ignore  # noqa: E402


def _package_claims(content: str) -> list[str]:
    claims = extract_claims(Path("dummy.md"), content)
    return [c["value"] for c in claims if c["type"] == "package-declaration"]


def test_from_import_produces_single_package_claim():
    content = (
        "```python\n"
        "from aspose_html.dom import Document\n"
        "```\n"
    )
    values = _package_claims(content)
    assert values == ["aspose_html.dom"], (
        f"Expected exactly one package claim for the module path, got {values}"
    )


def test_from_import_does_not_tag_imported_class_as_package():
    content = (
        "```python\n"
        "from aspose_html.cssom import CSSStyleSheet\n"
        "```\n"
    )
    values = _package_claims(content)
    assert "CSSStyleSheet" not in values, (
        "Imported class name must never be tagged as a package-declaration claim"
    )
    assert values == ["aspose_html.cssom"]


def test_from_import_multiple_names():
    content = (
        "```python\n"
        "from aspose_html.dom import Document, Element\n"
        "```\n"
    )
    values = _package_claims(content)
    assert values == ["aspose_html.dom"]
    assert "Document" not in values
    assert "Element" not in values


def test_bare_import_still_captured():
    content = (
        "```python\n"
        "import aspose_html.encoding.detection\n"
        "```\n"
    )
    values = _package_claims(content)
    assert values == ["aspose_html.encoding.detection"]


def test_pip_install_still_captured():
    content = (
        "```bash\n"
        "pip install aspose-html-foss\n"
        "```\n"
    )
    values = _package_claims(content)
    assert values == ["aspose-html-foss"]


def test_npm_install_option_is_not_misclassified_as_package():
    content = (
        "```bash\n"
        "npm install -D @aspose/3d\n"
        "```\n"
    )
    values = _package_claims(content)
    assert values == ["@aspose/3d"]
    assert "-D" not in values


def test_dotnet_using_still_captured():
    content = (
        "```csharp\n"
        "using Aspose.ThreeD;\n"
        "```\n"
    )
    values = _package_claims(content)
    assert values == ["Aspose.ThreeD"]


def test_repository_url_suffix_is_not_an_api_token():
    content = (
        "```bash\n"
        "git clone https://github.com/aspose-email-foss/"
        "Aspose.Email-FOSS-for-Cpp.git\n"
        "```\n"
    )
    claims = extract_claims(Path("installation.md"), content)
    assert not [
        claim for claim in claims
        if claim["type"] == "api-token" and claim["value"] == "Cpp.git"
    ]


def test_real_api_token_at_line_end_remains_captured():
    content = "```cpp\nMessage.load(path);\n```\n"
    claims = extract_claims(Path("example.md"), content)
    assert [
        claim for claim in claims
        if claim["type"] == "api-token" and claim["value"] == "Message.load"
    ]


def test_typescript_local_constant_member_is_not_an_api_token():
    content = "```typescript\nif (EXTENSIONS.includes(ext)) return;\n```\n"
    claims = extract_claims(Path("example.md"), content)
    assert not [
        claim for claim in claims
        if claim["type"] == "api-token" and claim["value"] == "EXTENSIONS.includes"
    ]


def test_typescript_language_extension_label_is_not_an_api_token():
    content = "```typescript\n// Integrate with Express.js middleware\n```\n"
    claims = extract_claims(Path("example.md"), content)
    assert not [
        claim for claim in claims
        if claim["type"] == "api-token" and claim["value"] == "Express.js"
    ]


def test_real_typescript_api_call_remains_captured():
    content = "```typescript\nconst scene = Scene.fromFile(input);\n```\n"
    claims = extract_claims(Path("example.md"), content)
    assert [
        claim for claim in claims
        if claim["type"] == "api-token" and claim["value"] == "Scene.fromFile"
    ]


def test_shell_activation_script_is_not_an_api_token():
    content = "```powershell\n.\\.venv\\Scripts\\Activate.ps1\n```\n"
    claims = extract_claims(Path("installation.md"), content)
    assert not [
        claim for claim in claims
        if claim["type"] == "api-token" and claim["value"] == "Activate.ps1"
    ]
