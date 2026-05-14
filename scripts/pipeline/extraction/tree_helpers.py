"""Shared extraction constants used by standalone reference scaffolding."""
from __future__ import annotations

PY_ENUM_BASES = frozenset({
    "Enum",
    "IntEnum",
    "StrEnum",
    "Flag",
    "IntFlag",
    "enum.Enum",
    "enum.IntEnum",
    "enum.StrEnum",
    "enum.Flag",
    "enum.IntFlag",
})

ENUM_KINDS = frozenset({
    "enum_specifier",
    "enum_declaration",
    "enum_definition",
})

CLASS_KINDS_BY_PLATFORM: dict[str, set[str]] = {
    "java": {"class_declaration", "interface_declaration"},
    "net": {"class_declaration", "interface_declaration", "struct_declaration", "record_declaration"},
    "cpp": {"class_specifier", "struct_specifier"},
    "python": {"class_definition"},
    "typescript": {"class_declaration", "interface_declaration", "type_alias_declaration"},
    "javascript": {"class_declaration"},
    "nodejs": {"class_declaration"},
}
