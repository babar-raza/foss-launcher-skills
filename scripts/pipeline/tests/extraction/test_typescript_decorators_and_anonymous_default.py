"""TC-TSGAP-11 / TC-TSGAP-12 (2026-09-24, Seventh Pass of the pdf/typescript
hardening plan): TypeScript decorator syntax and anonymous `export default`
forms were flagged by a fleet-gap audit as unclassified/unhandled. Live
investigation found:

- Decorators (TC-TSGAP-11): occupy their own tree-sitter field ('decorator'),
  never the 'declaration' field -- existing class_kinds/func_kinds
  extraction via child_by_field_name('declaration') already tolerates them.
  The declaration-kind census's own suffix heuristic (_DECL_SUFFIXES in
  test_declaration_kind_census.py) never flags 'decorator' in the first
  place (it isn't declaration-shaped), so there was no real census gap --
  but there was no direct proof a *decorated* class/method still extracts
  correctly. This file is that proof.
- Anonymous `export default` (TC-TSGAP-12): a real, narrow gap. A barrel
  file whose ONLY export is `export default function(){}` / `export default
  class {}` / `export default {...}` previously registered `found_any` as
  False in typescript.py's _collect_file_exports(), indistinguishable from a
  file with NO exports at all -- fixed via _EXPORT_DEFAULT_ANY_RE.
"""
from __future__ import annotations

from pathlib import Path

# sys.path is set by tests/conftest.py -- no manual insert needed here.
import scout
from extraction.api_surface import extract_api_surface
from extraction.tree_helpers import get_parser  # noqa: E402
from extraction.lang.typescript import _collect_file_exports  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "ts_flat_package"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_decorated_class_and_members_still_extracted_correctly(tmp_path):
    """A class-level + member-level decorated class extracts with the same
    name/member set as if the decorators weren't there at all."""
    pkg_root = tmp_path / "src"
    _write(pkg_root / "decorated.ts", (
        "function ServiceDecorator(_target: Function): void {}\n"
        "function TrackedDecorator(_target: unknown, _key: string): void {}\n\n"
        "@ServiceDecorator\n"
        "export class DecoratedService {\n"
        "  @TrackedDecorator\n"
        "  label: string = \"\";\n\n"
        "  @TrackedDecorator\n"
        "  run(): void {}\n"
        "}\n"
    ))
    parser = scout.get_parser("typescript")
    classes, *_ = extract_api_surface(parser, "typescript", pkg_root, tmp_path, "fake")
    by_name = {c["name"]: c for c in classes}

    assert "DecoratedService" in by_name, (
        "the class-level @ServiceDecorator must not prevent DecoratedService "
        "from being recognized as a class_declaration"
    )
    svc = by_name["DecoratedService"]
    member_names = {m["name"] for m in svc.get("methods", [])} | {
        p["name"] for p in svc.get("properties", [])
    }
    assert "label" in member_names, "the @TrackedDecorator-annotated field must still be captured"
    assert "run" in member_names, "the @TrackedDecorator-annotated method must still be captured"


def test_decorator_node_kind_does_not_break_declaration_shape_detection():
    """Direct tree-sitter proof that 'decorator' occupies its own field,
    never the 'declaration' field -- the structural fact the extraction
    code's field-based lookup relies on."""
    src = (
        b"@Foo()\nexport class Bar {}\n"
    )
    parser = get_parser("typescript")
    tree = parser.parse(src)
    export_stmt = tree.root_node.children[0]
    assert export_stmt.type == "export_statement"
    decl = export_stmt.child_by_field_name("declaration")
    assert decl is not None and decl.type == "class_declaration"
    decorator_field = export_stmt.child_by_field_name("decorator")
    assert decorator_field is not None and decorator_field.type == "decorator"


def test_anonymous_default_function_export_registers_as_a_real_export(tmp_path):
    f = tmp_path / "anon_fn.ts"
    f.write_text("export default function() {\n  return 1;\n}\n", encoding="utf-8")
    names, found_any = _collect_file_exports(f, set(), 0)
    assert found_any is True, "an anonymous default function export must count as a real export"
    assert names == set(), "no name should be fabricated for an anonymous export"


def test_anonymous_default_object_export_registers_as_a_real_export(tmp_path):
    f = tmp_path / "anon_obj.ts"
    f.write_text("export default {\n  greet: () => 'hi',\n};\n", encoding="utf-8")
    names, found_any = _collect_file_exports(f, set(), 0)
    assert found_any is True
    assert names == set()


def test_anonymous_default_new_expression_export_registers_as_a_real_export(tmp_path):
    f = tmp_path / "anon_new.ts"
    f.write_text("class Impl {}\nexport default new Impl();\n", encoding="utf-8")
    names, found_any = _collect_file_exports(f, set(), 0)
    assert found_any is True
    # "Impl" is a real class declared in this same file (via _EXPORT_DECL_RE
    # it would only be captured if exported itself, which it is not here) --
    # the anonymous default expression contributes no name either way.
    assert "Impl" not in names


def test_named_default_export_still_captures_its_name_unaffected(tmp_path):
    """Regression guard: the new anonymous-export catch-all must not change
    behavior for the already-handled named forms."""
    f = tmp_path / "named.ts"
    f.write_text("export default class Widget {}\n", encoding="utf-8")
    names, found_any = _collect_file_exports(f, set(), 0)
    assert found_any is True
    assert names == {"Widget"}


def test_file_with_no_export_at_all_still_registers_as_non_exporting(tmp_path):
    """Regression guard: the anonymous-export catch-all must not make a
    genuinely non-exporting file (the cells/typescript demo-index.ts shape)
    look like it has exports."""
    f = tmp_path / "demo.ts"
    f.write_text("console.log('just a script, no exports');\n", encoding="utf-8")
    names, found_any = _collect_file_exports(f, set(), 0)
    assert found_any is False
    assert names == set()
