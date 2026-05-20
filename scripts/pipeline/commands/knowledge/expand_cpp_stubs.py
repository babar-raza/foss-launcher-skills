# Adapted from aspose.org
"""expand_cpp_stubs.py — expand minimal email/cpp reference page stubs.

Replaces the 12-word placeholder overview with enriched descriptions
grounded in enriched_claims.json. Run from repo root:
    python scripts/pipeline/commands/knowledge/expand_cpp_stubs.py email cpp
"""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path

# Curated overviews built from enriched_claims (100% claim-grounded, no fabrication)
OVERVIEWS: dict[str, str] = {
    "cfb_document": (
        "`cfb_document` is the top-level container for a Compound File Binary document. "
        "It can be instantiated from a `cfb_reader`, a file path, an input stream, or a raw byte vector "
        "using its static `from_file`, `from_reader`, `from_stream`, and `from_bytes` factory methods. "
        "The class exposes getters and setters for the compound file's major version, minor version, "
        "and transaction signature number."
    ),
    "cfb_exception": (
        "`cfb_exception` is the exception type thrown when CFB parsing fails — for example when a container "
        "is malformed, truncated, or structurally invalid. "
        "Catch `cfb_exception` around any `cfb_reader` or `cfb_writer` call to handle parse failures without "
        "crashing the application."
    ),
    "cfb_node": (
        "`cfb_node` is the base node type for entries in a CFB directory hierarchy. "
        "It provides methods to query the node's kind, whether it is a storage or stream, "
        "read and modify state bits and timestamps, and clone the node for use elsewhere in the hierarchy."
    ),
    "cfb_reader": (
        "`cfb_reader` parses a Compound File Binary container and gives read access to its internal hierarchy. "
        "It provides metadata such as total data size, number of directory entries, and count of materialized streams. "
        "Navigation methods return vectors of storage, stream, and child IDs. "
        "`find_child_by_name` and `resolve_path` return `std::optional` values — "
        "callers must handle the case where a node is not found."
    ),
    "cfb_storage": (
        "`cfb_storage` represents a storage node (analogous to a directory) in a Compound File Binary hierarchy. "
        "It can be default-constructed to create a new empty storage container that can later be populated "
        "with stream nodes and serialized via `cfb_writer`."
    ),
    "cfb_stream": (
        "`cfb_stream` represents a stream node (analogous to a file) in a Compound File Binary hierarchy. "
        "It allows developers to set the raw byte content of a stream entry via `set_data` before the "
        "document is serialized using `cfb_writer`."
    ),
    "cfb_writer": (
        "`cfb_writer` serializes a `cfb_document` to a Compound File Binary byte representation. "
        "It can write the document to a `std::vector<uint8_t>` byte vector, to a file path, "
        "or directly to an `std::ostream` output stream."
    ),
    "directory_color_flag": (
        "`directory_color_flag` is a strongly-typed enum representing the color field of a CFB directory entry. "
        "Values correspond to the red/black tree coloring used internally by the CFB format to maintain "
        "directory ordering."
    ),
    "directory_entry": (
        "`directory_entry` represents a single entry in the CFB directory: either a storage container, "
        "a data stream, or the root storage. It carries the name, object type, timestamps, and associated "
        "identifiers as defined by the Compound File Binary specification."
    ),
    "directory_object_type": (
        "`directory_object_type` is a strongly-typed enum enumerating the object type byte stored in a CFB "
        "directory entry. Use its constants (`STORAGE_OBJECT`, `STREAM_OBJECT`, `ROOT_STORAGE_OBJECT`) to "
        "identify node types without inspecting raw bytes."
    ),
    "sector_marker": (
        "`sector_marker` is a strongly-typed enum holding reserved sector ID values used in the CFB format "
        "to mark special sectors such as free sectors and end-of-chain markers. "
        "Compare sector addresses against these constants when traversing the sector allocation table."
    ),
    "common_message_property_id": (
        "`common_message_property_id` is a strongly-typed enum representing standard MAPI property identifiers "
        "for MSG message objects. Use its values to look up typed properties from a `mapi_property_collection` "
        "without hard-coding raw integer property tags."
    ),
    "mapi_attachment": (
        "`mapi_attachment` represents a file attachment embedded in a MAPI message. "
        "It can be created from a byte array or input stream, can load its binary data payload, "
        "and provides a flag indicating whether the attachment contains an embedded message."
    ),
    "mapi_message": (
        "`mapi_message` is the primary class for reading and writing Outlook MSG messages. "
        "It can be instantiated from a file path, an input stream, an existing `msg_document`, or an EML file. "
        "After setting the subject, body, sender, and recipients it can be saved to a byte vector, a file, "
        "or an output stream via `save()`, or converted to a `msg_document` via `to_msg_document()`."
    ),
    "mapi_property": (
        "`mapi_property` represents a single typed MAPI property in a message or attachment. "
        "It gives access to the property's identifier, type code, raw tag, and flags, "
        "and allows overwriting the property value for custom modifications before saving."
    ),
    "mapi_property_collection": (
        "`mapi_property_collection` manages the set of MAPI properties attached to a message or attachment. "
        "It supports removal of individual properties from the property set, enabling lightweight trimming "
        "of unnecessary metadata before serializing the message."
    ),
    "mapi_recipient": (
        "`mapi_recipient` represents a message recipient (To, CC, or BCC) in a MAPI message. "
        "It holds the recipient display name, email address, and recipient type as stored in the MSG format."
    ),
    "msg_document": (
        "`msg_document` is the low-level representation of an Outlook MSG file. "
        "It can be constructed from a `msg_reader`, a file path, or an input stream. "
        "The class exposes the MSG file's major version, minor version, transaction signature number, "
        "and strict-mode flag, and can be converted into a `cfb_document` for raw CFB manipulation."
    ),
    "msg_exception": (
        "`msg_exception` is the exception type thrown when MSG parsing fails. "
        "Catch `msg_exception` around any `msg_reader` or `msg_document` construction call to handle "
        "malformed or unsupported MSG files gracefully."
    ),
    "msg_reader": (
        "`msg_reader` parses an Outlook MSG file and provides access to the underlying `msg_document`. "
        "It can be instantiated from a file path or an input stream with an optional strict parsing mode, "
        "and the current strict mode can be queried via `strict()`."
    ),
    "msg_storage": (
        "`msg_storage` represents a storage node (sub-container) within an MSG file's internal CFB structure. "
        "It mirrors a `cfb_storage` in the underlying Compound File Binary representation "
        "and is used for internal traversal of MSG file sub-structures."
    ),
    "msg_storage_role": (
        "`msg_storage_role` is a strongly-typed enum classifying the purpose of a storage node in an MSG file: "
        "for example, identifying whether a storage holds attachment data, recipient tables, "
        "or other message sub-structures."
    ),
    "msg_stream": (
        "`msg_stream` represents a stream data node within an MSG file's internal CFB structure. "
        "It carries the raw binary data of a single MSG stream entry, mirroring a `cfb_stream` "
        "in the underlying Compound File Binary representation."
    ),
    "msg_writer": (
        "MSG content is written by calling `mapi_message::save()` directly — there is no separate "
        "`msg_writer` class in the public API. This page documents the `msg_writer` internal type "
        "present in the library headers for reference completeness."
    ),
    "property_type_code": (
        "`property_type_code` is a strongly-typed enum encoding the MAPI property type byte. "
        "Its values (e.g. `PT_UNICODE`, `PT_BINARY`, `PT_LONG`) identify the data type of a "
        "`mapi_property`, matching the low 16 bits of the MAPI property tag."
    ),
    "header": (
        "`header` exposes the binary header of a Compound File Binary document, including sector size, "
        "mini-stream cutoff, and DIFAT array fields as defined by the CFB specification. "
        "It is used internally by `cfb_reader` to validate and navigate the document structure."
    ),
}

# Pattern: "`class` is a class/enum in Aspose.Email FOSS for C++.\n  \nDefined in: ..."
# or just the first sentence followed by defined-in
STUB_INTRO_RE = re.compile(
    r"`[^`]+` is (?:a|an) (?:class|enum|exception) in Aspose\.Email FOSS for C\+\+\.",
    re.DOTALL,
)


def expand(family: str, platform: str) -> None:
    content_root = os.environ.get("CONTENT_ROOT", "content")
    ref_dir = Path(content_root) / "reference.aspose.org" / "en" / family / platform
    updated: list[str] = []
    skipped: list[str] = []

    for md_file in sorted(ref_dir.glob("*.md")):
        if md_file.name == "_index.md":
            continue

        content = md_file.read_text(encoding="utf-8")

        # Find linkTitle
        m = re.search(r"^linkTitle:\s*(.+)", content, re.MULTILINE)
        if not m:
            skipped.append(f"{md_file.name} (no linkTitle)")
            continue
        class_name = m.group(1).strip().strip('"\'')

        if class_name not in OVERVIEWS:
            skipped.append(f"{md_file.name} (class {class_name!r} not in OVERVIEWS)")
            continue

        # Only replace if stub intro is present
        intro_match = STUB_INTRO_RE.search(content)
        if not intro_match:
            skipped.append(f"{md_file.name} (already expanded)")
            continue

        new_intro = OVERVIEWS[class_name]
        new_content = content[:intro_match.start()] + new_intro + content[intro_match.end():]
        md_file.write_text(new_content, encoding="utf-8")
        updated.append(md_file.name)

    print(f"Updated ({len(updated)}): {', '.join(updated)}")
    print(f"Skipped ({len(skipped)}): {', '.join(skipped)}")


if __name__ == "__main__":
    family = sys.argv[1] if len(sys.argv) > 1 else "email"
    platform = sys.argv[2] if len(sys.argv) > 2 else "cpp"
    expand(family, platform)
