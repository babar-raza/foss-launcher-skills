"""HARDEN-cpp-enum-x-suffix (MT012): C++ `ClassName::MEMBER` enum access with a
lowercase "x<digits>" bit-width suffix.

Found live while writing pdf/cpp's products page: `CryptoAlgorithm` encodes its
4 members as `RC4x40, RC4x128, AESx128, AESx256` (crypto_algorithm.hpp) — a real,
correct enum value the pure ALL_CAPS `_CPP_ENUM_ACCESS` regex could not match.
`Aspose::Pdf::CryptoAlgorithm::AESx256` was mis-parsed as member "AES" (the regex
greedily matched only the ALL_CAPS prefix, silently dropping "x256"), which then
failed audit as "enum member not found" for genuine, correct code.
"""
import tempfile
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
from token_ops import _extract_from_code_line, extract_tokens, verify_tokens


def _make_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


class _FakeKnowledge:
    """Minimal stand-in for knowledge_core.Knowledge, enum-path only."""

    def __init__(self, classes: dict[str, set[str]]):
        self.platform = "cpp"
        self.surface_tier = 1
        self.classes = set(classes)
        self.enum_members = classes
        self.methods = {}
        self.properties = {}
        self.valid_imports = set()

    def has_property(self, cls, name):
        return False

    def has_enum_member(self, cls, name):
        return name in self.enum_members.get(cls, set())

    def closest_match(self, actual, name):
        return []


class TestCppEnumAccessXSuffix:
    """_extract_from_code_line must extract the full ALLCAPSxDIGITS member."""

    @pytest.mark.parametrize("member", ["RC4x40", "RC4x128", "AESx128", "AESx256"])
    def test_extracts_full_x_suffixed_member(self, member):
        var_types: dict = {}
        tokens = _extract_from_code_line(
            f"doc.Encrypt(user, owner, perms, Aspose::Pdf::CryptoAlgorithm::{member});",
            1, var_types, "cpp",
        )
        enum_tokens = [(t.class_name, t.member_name) for t in tokens if t.kind == "enum"]
        assert ("CryptoAlgorithm", member) in enum_tokens

    def test_plain_all_caps_member_unaffected(self):
        """Regression guard: the original pure ALL_CAPS idiom (no x-suffix) must
        keep working exactly as before."""
        var_types: dict = {}
        tokens = _extract_from_code_line(
            "auto f = FillType::SOLID;", 1, var_types, "cpp",
        )
        enum_tokens = [(t.class_name, t.member_name) for t in tokens if t.kind == "enum"]
        assert ("FillType", "SOLID") in enum_tokens

    def test_mixed_case_static_method_call_not_misread_as_enum(self):
        """DocumentInfo::IsPredefinedKey is a static method call, not an enum
        access — the mandatory 2+-char ALL_CAPS core must still exclude it."""
        var_types: dict = {}
        tokens = _extract_from_code_line(
            'bool ok = Aspose::Pdf::DocumentInfo::IsPredefinedKey("Title");',
            1, var_types, "cpp",
        )
        assert not [t for t in tokens if t.kind == "enum"]

    def test_not_extracted_on_python_platform(self):
        """The cpp/rust :: patterns are platform-gated — Python has no enum-access
        extraction of this shape at all."""
        var_types: dict = {}
        tokens = _extract_from_code_line(
            "v = CryptoAlgorithm::AESx256", 1, var_types, "python",
        )
        assert not [t for t in tokens if t.kind == "enum"]


class TestCppEnumAccessXSuffixEndToEnd:
    """extract_tokens + verify_tokens over a real fenced cpp block."""

    def test_confirmed_x_suffixed_member_produces_no_fail(self):
        md = _make_md(
            "```cpp\n"
            "doc.Encrypt(\"u\", \"o\", Aspose::Pdf::Permissions(),\n"
            "            Aspose::Pdf::CryptoAlgorithm::AESx256);\n"
            "```\n"
        )
        tokens = extract_tokens(md, "cpp")
        knowledge = _FakeKnowledge({"CryptoAlgorithm": {"RC4x40", "RC4x128", "AESx128", "AESx256"}})
        findings = verify_tokens(tokens, knowledge, md)
        assert not [f for f in findings if f.level == "FAIL"]
        md.unlink()
