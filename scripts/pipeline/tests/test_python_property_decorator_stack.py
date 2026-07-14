"""Tests for stacked-decorator @property detection in api_surface.py (ST-014).

Regression coverage for the font/python truth audit finding (S-38,
2026-07-14): `_extract_python_properties()` and the method-extraction
skip-check both only inspected the single nearest decorator (a direct
child of the function node, or its one immediate previous sibling). A
method declared `@property` stacked with `@abstractmethod` — where
`@abstractmethod` is the nearest sibling — was never recognized as a
property and fell through to plain-method extraction, producing content
that tells callers to invoke `font.font_name()` when the real API is a
property accessed as `font.font_name`.
"""
from extraction.api_surface import _all_decorator_text, _extract_python_properties
from extraction.tree_helpers import collect_nodes, get_parser


def _parse_class(code: str):
    parser = get_parser("python")
    root = parser.parse(code.encode("utf-8")).root_node
    classes = collect_nodes(root, {"class_definition"})
    return classes[0]


STACKED_ABSTRACT_PROPERTY = """
class Font:
    @property
    @abstractmethod
    def font_name(self) -> str:
        '''The font's name.'''
        ...

    @abstractmethod
    def get_glyph(self, code: int):
        ...
"""

PLAIN_PROPERTY = """
class CffFont(Font):
    @property
    def font_name(self) -> str:
        '''The font's name.'''
        return self._name
"""

WRITABLE_STACKED_PROPERTY = """
class Widget:
    @property
    @some_other_decorator
    def value(self) -> int:
        return self._value

    @value.setter
    @some_other_decorator
    def value(self, v: int) -> None:
        self._value = v
"""


# ---------------------------------------------------------------------------
# _all_decorator_text — the shared helper
# ---------------------------------------------------------------------------


def test_all_decorator_text_finds_property_stacked_with_abstractmethod():
    cls = _parse_class(STACKED_ABSTRACT_PROPERTY)
    func = collect_nodes(cls, {"function_definition"})[0]
    text = _all_decorator_text(func)
    assert "@property" in text
    assert "@abstractmethod" in text


def test_all_decorator_text_handles_single_decorator():
    cls = _parse_class(PLAIN_PROPERTY)
    func = collect_nodes(cls, {"function_definition"})[0]
    text = _all_decorator_text(func)
    assert "@property" in text


# ---------------------------------------------------------------------------
# _extract_python_properties — the actual regression
# ---------------------------------------------------------------------------


def test_stacked_property_and_abstractmethod_is_classified_as_property():
    cls = _parse_class(STACKED_ABSTRACT_PROPERTY)
    properties, _claims = _extract_python_properties(cls, "Font", "font.py", "font")
    names = {p["name"] for p in properties}
    assert "font_name" in names, (
        "@property stacked with @abstractmethod must be extracted as a property, "
        "not silently dropped and left to fall through to method extraction"
    )


def test_plain_abstractmethod_without_property_is_not_a_property():
    cls = _parse_class(STACKED_ABSTRACT_PROPERTY)
    properties, _claims = _extract_python_properties(cls, "Font", "font.py", "font")
    names = {p["name"] for p in properties}
    assert "get_glyph" not in names


def test_unstacked_property_still_works():
    cls = _parse_class(PLAIN_PROPERTY)
    properties, _claims = _extract_python_properties(cls, "CffFont", "font.py", "font")
    names = {p["name"] for p in properties}
    assert "font_name" in names


def test_stacked_setter_marks_property_writable():
    cls = _parse_class(WRITABLE_STACKED_PROPERTY)
    properties, _claims = _extract_python_properties(cls, "Widget", "widget.py", "widget")
    value_prop = next((p for p in properties if p["name"] == "value"), None)
    assert value_prop is not None
    assert value_prop["writable"] is True, (
        "a @value.setter stacked with another decorator must still register as a setter"
    )
