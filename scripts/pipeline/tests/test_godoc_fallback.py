"""Tests for the Go doc name-inference fallback (_apply_godoc_fallback, _camel_to_words).

These functions are defined in promote.py and solve GODOC-GO-001: 117 pdf/go methods
with empty doc fields whose upstream Go source has no // comments.  Name inference
generates deterministic, auditable descriptions from method name patterns.

conftest.py adds commands/knowledge/ to sys.path so bare imports work.
"""
from promote import _apply_godoc_fallback, _camel_to_words


# ---------------------------------------------------------------------------
# _camel_to_words
# ---------------------------------------------------------------------------

def test_camel_simple():
    assert _camel_to_words("TextStyle") == "text style"


def test_camel_all_caps():
    assert _camel_to_words("URL") == "url"


def test_camel_all_caps_followed_by_word():
    # URLPath → URL Path → url path
    assert _camel_to_words("URLPath") == "url path"


def test_camel_single_word():
    assert _camel_to_words("Text") == "text"


def test_camel_read_only():
    assert _camel_to_words("ReadOnly") == "read only"


def test_camel_multiline():
    assert _camel_to_words("Multiline") == "multiline"


def test_camel_default_cell_border():
    assert _camel_to_words("DefaultCellBorder") == "default cell border"


# ---------------------------------------------------------------------------
# _apply_godoc_fallback — platform guard
# ---------------------------------------------------------------------------

def test_no_op_for_non_go_platform():
    api = [{"name": "Cell", "methods": [{"name": "SetText", "doc": "", "params": [{"name": "t"}], "return_type": ""}]}]
    count = _apply_godoc_fallback(api, "python")
    assert count == 0
    assert api[0]["methods"][0]["doc"] == ""  # unchanged


def test_no_op_for_java_platform():
    api = [{"name": "Cell", "methods": [{"name": "SetText", "doc": "", "params": [{"name": "t"}], "return_type": ""}]}]
    count = _apply_godoc_fallback(api, "java")
    assert count == 0


# ---------------------------------------------------------------------------
# Setter pattern: Set{Name}(val) → "Sets the {name} value."
# ---------------------------------------------------------------------------

def _method(name, doc="", params=None, return_type=""):
    return {"name": name, "doc": doc, "params": params or [], "return_type": return_type}


def _api(class_name="Cell", methods=None):
    return [{"name": class_name, "methods": methods or []}]


def test_setter_infers_description():
    api = _api(methods=[_method("SetText", params=[{"name": "text"}])])
    count = _apply_godoc_fallback(api, "go")
    assert count == 1
    assert api[0]["methods"][0]["doc"] == "Sets the text value."


def test_setter_marks_doc_source():
    api = _api(methods=[_method("SetText", params=[{"name": "text"}])])
    _apply_godoc_fallback(api, "go")
    assert api[0]["methods"][0]["doc_source"] == "name_inference"


def test_setter_multiword():
    api = _api(methods=[_method("SetTextStyle", params=[{"name": "s"}])])
    _apply_godoc_fallback(api, "go")
    assert api[0]["methods"][0]["doc"] == "Sets the text style value."


def test_setter_url():
    api = _api(methods=[_method("SetURL", params=[{"name": "u"}])])
    _apply_godoc_fallback(api, "go")
    assert api[0]["methods"][0]["doc"] == "Sets the url value."


def test_setter_no_params_not_inferred():
    # A Set* method with no params is unusual — don't infer
    api = _api(methods=[_method("SetText", params=[])])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0
    assert api[0]["methods"][0]["doc"] == ""


def test_set_prefix_only_not_inferred():
    # "Set" alone is not a valid setter name
    api = _api(methods=[_method("Set", params=[{"name": "v"}])])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0


# ---------------------------------------------------------------------------
# Is/Has pattern
# ---------------------------------------------------------------------------

def test_is_prefix_infers_description():
    api = _api(methods=[_method("IsMultiline", return_type="bool")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 1
    assert api[0]["methods"][0]["doc"] == "Returns true if multiline is set."


def test_has_prefix_infers_description():
    api = _api(methods=[_method("HasTop", return_type="bool")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 1
    assert api[0]["methods"][0]["doc"] == "Returns true if top is present."


def test_is_with_params_not_inferred():
    # Is* with params → not a standard predicate; skip
    api = _api(methods=[_method("IsType", params=[{"name": "t"}], return_type="bool")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0


def test_is_prefix_only_falls_through_to_getter():
    # "Is" alone (len==2) doesn't match the Is-prefix predicate branch;
    # falls through to the generic getter → "Returns the is."
    api = _api(methods=[_method("Is", return_type="bool")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 1
    assert api[0]["methods"][0]["doc"] == "Returns the is."


# ---------------------------------------------------------------------------
# Generic getter pattern: {Name}() T → "Returns the {name}."
# ---------------------------------------------------------------------------

def test_getter_infers_description():
    api = _api(methods=[_method("Text", return_type="string")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 1
    assert api[0]["methods"][0]["doc"] == "Returns the text."


def test_getter_action_type():
    api = _api(methods=[_method("ActionType", return_type="ActionType")])
    _apply_godoc_fallback(api, "go")
    assert api[0]["methods"][0]["doc"] == "Returns the action type."


def test_getter_void_return_not_inferred():
    # No return type → not a getter
    api = _api(methods=[_method("Draw", return_type="")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0


def test_getter_error_return_not_inferred():
    # error return → likely a command, not a getter
    api = _api(methods=[_method("Validate", return_type="error")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0


def test_getter_with_params_not_inferred():
    # Has params → not a simple getter
    api = _api(methods=[_method("GetAt", params=[{"name": "idx"}], return_type="string")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0


# ---------------------------------------------------------------------------
# Existing doc not overwritten
# ---------------------------------------------------------------------------

def test_existing_doc_not_overwritten():
    original_doc = "Count reports how many annotations live on this page."
    api = _api(methods=[_method("Count", doc=original_doc, return_type="int")])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0
    assert api[0]["methods"][0]["doc"] == original_doc


def test_existing_doc_source_not_overwritten():
    # Even if a method already has doc_source: name_inference from a prior run,
    # a non-empty doc is never re-generated
    api = _api(methods=[{
        "name": "Text",
        "doc": "Returns the text.",
        "doc_source": "name_inference",
        "params": [],
        "return_type": "string",
    }])
    count = _apply_godoc_fallback(api, "go")
    assert count == 0  # already has a doc


# ---------------------------------------------------------------------------
# Multiple methods across multiple classes
# ---------------------------------------------------------------------------

def test_multiple_empty_methods_all_inferred():
    api = [
        {"name": "Cell", "methods": [
            _method("SetText", params=[{"name": "t"}]),
            _method("Text", return_type="string"),
        ]},
        {"name": "Table", "methods": [
            _method("IsMultiline", return_type="bool"),
            _method("HasLeft", return_type="bool"),
        ]},
    ]
    count = _apply_godoc_fallback(api, "go")
    assert count == 4


def test_mixed_empty_and_documented():
    api = _api(methods=[
        _method("Count", doc="Count reports how many items.", return_type="int"),
        _method("Text", return_type="string"),
    ])
    count = _apply_godoc_fallback(api, "go")
    assert count == 1
    assert api[0]["methods"][0]["doc"] == "Count reports how many items."
    assert api[0]["methods"][1]["doc"] == "Returns the text."


# ---------------------------------------------------------------------------
# Idempotency — running twice produces same result
# ---------------------------------------------------------------------------

def test_idempotent_second_run_no_change():
    api = _api(methods=[_method("SetText", params=[{"name": "t"}])])
    count1 = _apply_godoc_fallback(api, "go")
    count2 = _apply_godoc_fallback(api, "go")
    assert count1 == 1
    assert count2 == 0  # doc already set → not re-inferred
    assert api[0]["methods"][0]["doc"] == "Sets the text value."
