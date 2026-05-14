import json

import pytest

from scripts.pipeline.commands.content import ground_check


@pytest.fixture(autouse=True)
def reset_ground_check():
    yield
    ground_check.configure()


def _knowledge(tmp_path):
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)
    path = merged / "api_surface.json"
    path.write_text(
        json.dumps([
            {
                "name": "Scene",
                "methods": [{"name": "open"}, {"name": "save"}],
                "properties": [{"name": "root_node"}],
                "enum_members": [{"name": "OBJ"}],
            }
        ]),
        encoding="utf-8",
    )
    ground_check.configure(repo_root=tmp_path)
    return path


def test_known_identifier_builder_supports_methods_properties_and_enums():
    known = ground_check._build_known_identifiers([
        {
            "name": "Scene",
            "method_details": [{"name": "open"}],
            "property_details": [{"name": "root_node"}],
            "enum_members": [{"name": "OBJ"}],
        }
    ])

    assert {"scene", "open", "root_node", "obj"}.issubset(known)


def test_all_identifiers_matched(tmp_path):
    api = _knowledge(tmp_path)
    page = tmp_path / "page.md"
    page.write_text("Use `Scene`, `Scene.open`, and `Scene.save`.", encoding="utf-8")

    ratio, matched, total, ungrounded = ground_check.compute_grounding_ratio(page, api)

    assert ratio == 1.0
    assert matched == total == 3
    assert ungrounded == []


def test_frontmatter_identifiers_are_ignored(tmp_path):
    api = _knowledge(tmp_path)
    page = tmp_path / "page.md"
    page.write_text("---\ndescription: '`Unknown`'\n---\n\nUse `Scene`.", encoding="utf-8")

    ratio, matched, total, _ = ground_check.compute_grounding_ratio(page, api)

    assert ratio == 1.0
    assert matched == total == 1


def test_warn_and_fail_exit_codes(tmp_path):
    _knowledge(tmp_path)
    warn_page = tmp_path / "warn.md"
    warn_page.write_text("`Scene` `Scene.open` `Scene.save` `UnknownThing`", encoding="utf-8")
    fail_page = tmp_path / "fail.md"
    fail_page.write_text("`Scene` `A` `B` `C` `D`", encoding="utf-8")

    assert ground_check.main(["fake", "python", str(warn_page)]) == 1
    assert ground_check.main(["fake", "python", str(fail_page)]) == 2


def test_no_identifiers_passes(tmp_path):
    _knowledge(tmp_path)
    page = tmp_path / "page.md"
    page.write_text("Plain prose.", encoding="utf-8")

    assert ground_check.main(["fake", "python", str(page)]) == 0


def test_missing_api_surface_fails(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("`Scene`", encoding="utf-8")
    ground_check.configure(repo_root=tmp_path)

    assert ground_check.main(["fake", "python", str(page)]) == 2
