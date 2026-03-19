"""Shared JSON schema validation helper.

Usage:
    from schema_validate import validate

    errors = validate(data, "pef")  # validates against configs/schemas/pef.schema.json
    if errors:
        print("Validation failed:", errors)
"""
import json
from pathlib import Path

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "configs" / "schemas"

_cache: dict[str, dict] = {}


def load_schema(name: str) -> dict:
    """Load a JSON schema by name from configs/schemas/{name}.schema.json."""
    if name in _cache:
        return _cache[name]
    path = SCHEMAS_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    _cache[name] = schema
    return schema


def validate(data: dict, schema_name: str) -> list[str]:
    """Validate data against a named schema.

    Returns a list of error messages (empty = valid).
    Uses jsonschema if available, otherwise falls back to structural checks.
    """
    schema = load_schema(schema_name)
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        return [e.message for e in validator.iter_errors(data)]
    except ImportError:
        return _structural_validate(data, schema)


def _structural_validate(data: dict, schema: dict) -> list[str]:
    """Fallback structural validation when jsonschema is not installed."""
    errors = []
    if not isinstance(data, dict):
        return ["Root must be an object"]

    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"Missing required field: {field}")

    props = schema.get("properties", {})
    for field, spec in props.items():
        if field not in data:
            continue
        value = data[field]
        expected = spec.get("type")
        if expected and not _type_matches(value, expected):
            errors.append(f"Field '{field}' expected type {expected}, got {type(value).__name__}")

    return errors


def _type_matches(value, expected) -> bool:
    """Check if value matches JSON schema type spec."""
    if isinstance(expected, list):
        return any(_type_matches(value, t) for t in expected)
    mapping = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    py_type = mapping.get(expected)
    if py_type is None:
        return True
    if expected == "integer" and isinstance(value, bool):
        return False
    return isinstance(value, py_type)
