"""extraction/ — scout.py extraction helpers split into focused modules.

This package contains the standalone (non-Scout-class) functions extracted
from scout.py. Import them here for a clean public interface, or import
from the sub-modules directly.

Backward-compat: scout.py re-exports everything from these modules so
existing `import scout; scout.get_parser(...)` call sites continue to work.
"""
from .tree_helpers import (
    PLATFORM_TO_LANG,
    _CLASS_TYPES,
    _FUNC_TYPES,
    _PY_ENUM_BASES,
    _IMPORT_TYPES,
    _MODULE_TYPES,
    _NOT_IMPL_PATTERNS,
    _FILE_EXTENSIONS,
    _HEADER_EXTENSIONS,
    _DOC_COMMENT_STYLES,
    _LANG_ALIASES,
    get_parser,
    collect_nodes,
    node_text,
    child_by_field,
    find_child_by_type,
    find_children_by_type,
    _node_name,
    is_public,
)
from .package_root import detect_package_root
from .package_manifest import parse_manifest

__all__ = [
    "PLATFORM_TO_LANG",
    "_CLASS_TYPES",
    "_FUNC_TYPES",
    "_PY_ENUM_BASES",
    "_IMPORT_TYPES",
    "_MODULE_TYPES",
    "_NOT_IMPL_PATTERNS",
    "_FILE_EXTENSIONS",
    "_HEADER_EXTENSIONS",
    "_DOC_COMMENT_STYLES",
    "_LANG_ALIASES",
    "get_parser",
    "collect_nodes",
    "node_text",
    "child_by_field",
    "find_child_by_type",
    "find_children_by_type",
    "_node_name",
    "is_public",
    "detect_package_root",
    "parse_manifest",
]
