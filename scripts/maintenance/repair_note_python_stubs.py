"""Fix note/python stub reference pages: add prose overviews and enum descriptions."""
import re
from pathlib import Path

REF = Path("content/reference.aspose.org/en/note/python")

UPDATES = {
    "AsposeNoteError.md": {
        "old": "AsposeNoteError — AsposeNoteError class in the Aspose.Note FOSS Python API.. Inherits from: `Exception`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`AsposeNoteError` is the base exception class for all errors raised by the Aspose.Note FOSS Python library. It inherits from the built-in Python `Exception` class. Catch `AsposeNoteError` to handle any library-specific failure in a single `except` block, or catch a more specific subclass such as `FileCorruptedException` or `IncorrectPasswordException` when you need fine-grained error handling.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "FileCorruptedException.md": {
        "old": "FileCorruptedException — FileCorruptedException class in the Aspose.Note FOSS Python API.. Inherits from: `AsposeNoteError`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`FileCorruptedException` is raised when Aspose.Note encounters a OneNote file whose binary structure is damaged, truncated, or otherwise unreadable. It inherits from `AsposeNoteError`. Catch this exception when calling `Document()` to detect corrupt `.one` files and report a meaningful error to the user instead of propagating a raw I/O failure.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "IncorrectDocumentStructureException.md": {
        "old": "IncorrectDocumentStructureException — IncorrectDocumentStructureException class in the Aspose.Note FOSS Python API.. Inherits from: `AsposeNoteError`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`IncorrectDocumentStructureException` is raised when a OneNote document fails internal structural validation — for example, a required section or notebook hierarchy node is missing or malformed. It inherits from `AsposeNoteError`. Handle this exception to detect files that are syntactically valid at the binary level but do not conform to the expected document object model.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "IncorrectPasswordException.md": {
        "old": "IncorrectPasswordException — IncorrectPasswordException class in the Aspose.Note FOSS Python API.. Inherits from: `AsposeNoteError`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`IncorrectPasswordException` is raised when you attempt to open a password-protected OneNote file and the supplied password does not match. It inherits from `AsposeNoteError`. Pass the correct password via `LoadOptions.document_password` before constructing `Document()`; catch this exception to prompt the user for a retry without crashing.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "UnsupportedSaveFormatException.md": {
        "old": "UnsupportedSaveFormatException — UnsupportedSaveFormatException class in the Aspose.Note FOSS Python API.. Inherits from: `AsposeNoteError`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`UnsupportedSaveFormatException` is raised when `Document.save()` is called with a `SaveFormat` value that the current library version does not support for export. It inherits from `AsposeNoteError`. The FOSS edition currently supports `SaveFormat.Pdf` only; catch this exception when writing code that may target multiple export formats to give a clear diagnostic message.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "UnsupportedFileFormatException.md": {
        "old": "UnsupportedFileFormatException — UnsupportedFileFormatException class in the Aspose.Note FOSS Python API.. Inherits from: `AsposeNoteError`.\n\n**Package**: `aspose.note`",
        "new": "## Overview\n\n`UnsupportedFileFormatException` is raised when `Document()` is asked to load a OneNote file whose format version is not recognised by the library. It inherits from `AsposeNoteError`. Inspect the `FileFormat` property to determine which `FileFormat` enum value was detected; the FOSS edition supports `OneNote2010` and `OneNoteOnline` notebooks.\n\n**Package**: `aspose.note`",
    },
    "FileFormat.md": {
        "old": "FileFormat — FileFormat class in the Aspose.Note FOSS Python API..",
        "new": "## Overview\n\n`FileFormat` is an enumeration that identifies the version of a OneNote file. Use it to check which format a loaded document uses, or to filter files before passing them to `Document()`. `UnsupportedFileFormatException.FileFormat` returns one of these values when loading fails.",
    },
    "HorizontalAlignment.md": {
        "old": "HorizontalAlignment — HorizontalAlignment class in the Aspose.Note FOSS Python API..",
        "new": "## Overview\n\n`HorizontalAlignment` is an enumeration specifying the horizontal text or element alignment within a container such as `TableCell`. Assign one of its values — `Left`, `Center`, or `Right` — to alignment properties on nodes that support layout configuration.",
    },
    "NodeType.md": {
        "old": "NodeType — NodeType class in the Aspose.Note FOSS Python API..",
        "new": "## Overview\n\n`NodeType` is an enumeration that identifies the concrete type of a node in the OneNote document object model. Each class in the DOM — `Document`, `Page`, `Outline`, `OutlineElement`, `RichText`, `Image`, `Table`, `AttachedFile` — corresponds to a `NodeType` constant. Use it with visitor callbacks or type checks to dispatch logic without relying on `isinstance` calls.",
    },
    "SaveFormat.md": {
        "old": "SaveFormat — SaveFormat class in the Aspose.Note FOSS Python API..",
        "new": "## Overview\n\n`SaveFormat` is an enumeration listing the output formats supported by `Document.save()`. In the current FOSS release only `SaveFormat.Pdf` is available. Pass a `SaveFormat` value as the second argument to `Document.save(path, save_format)`, or set it on a `SaveOptions` instance before calling save.",
    },
    "SaveOptions.md": {
        "old": "SaveOptions — SaveOptions class in the Aspose.Note FOSS Python API..",
        "new": "## Overview\n\n`SaveOptions` is the base configuration class for document export operations. Set `SaveOptions.SaveFormat` to the desired `SaveFormat` enum value before passing the instance to `Document.save()`. Subclasses such as `PdfSaveOptions` extend this base with format-specific settings like page range and image compression.",
    },
    "License.md": {
        "old": "License — License class in the Aspose.Note FOSS Python API..",
        "new": "## Overview\n\n`License` manages API activation for the Aspose.Note FOSS Python library. Call `License.SetLicense()` with a path to your `.lic` file or a stream containing the license XML before performing any document operations. Without a valid license the library runs in evaluation mode, which places a watermark on exported documents.",
    },
    "Metered.md": {
        "old": "Metered — Metered class in the Aspose.Note FOSS Python API..",
        "new": "## Overview\n\n`Metered` enables consumption-based licensing for Aspose.Note. Call `Metered.SetMeteredKey()` with your public and private key strings at application startup to activate metered billing instead of a traditional license file. Usage is tracked by Aspose servers and billed according to the number of API calls and pages processed.",
    },
    "LoadOptions.md": {
        "old": "LoadOptions — LoadOptions class in the Aspose.Note FOSS Python API..\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`LoadOptions` configures how a `.one` file is opened by `Document()`. Use it to supply a password for encrypted notebooks via the `document_password` property, or to control which page range to load. Pass a `LoadOptions` instance as the second argument to the `Document` constructor.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "OutlineElement.md": {
        "old": "OutlineElement — OutlineElement class in the Aspose.Note FOSS Python API.. Inherits from: `CompositeNode`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`OutlineElement` is a container node that holds the content items within an `Outline` section of a OneNote page. It inherits from `CompositeNode` and can contain child nodes of type `RichText`, `Image`, `AttachedFile`, or nested outlines. Iterate `OutlineElement` children to extract every content fragment from a page element.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "TableCell.md": {
        "old": "TableCell — TableCell class in the Aspose.Note FOSS Python API.. Inherits from: `CompositeNode`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`TableCell` represents a single cell within a `TableRow` in a OneNote table. It inherits from `CompositeNode` and may contain `RichText` nodes as child content. Enumerate the child nodes of a `TableCell` to read the text, images, or attachments stored in that cell.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "TableRow.md": {
        "old": "TableRow — TableRow class in the Aspose.Note FOSS Python API.. Inherits from: `CompositeNode`.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
        "new": "## Overview\n\n`TableRow` represents a single row within a `Table` node in a OneNote document. It inherits from `CompositeNode` and contains one or more `TableCell` child nodes. Iterate the child nodes of a `TableRow` to access individual cells and their content when traversing table data.\n\n**Package**: `aspose.note`\n\n---\n\nNo public API members documented in source.",
    },
    "table.md": {
        "old": "`Table` — Table class in the Aspose.Note FOSS Python API. Inherits from: `CompositeNode`.",
        "new": "`Table` represents a structured table in a OneNote page. It inherits from `CompositeNode` and contains `TableRow` children, each holding `TableCell` nodes with `RichText` content. Use `Table.IsBordersVisible` to control border rendering and `Table.Columns` to access column width metadata.",
    },
}

ENUM_DESCRIPTIONS = {
    "FileFormat.md": {
        "Unknown": "Format could not be determined or the file is not a recognised OneNote file.",
        "OneNote2010": "OneNote 2010 desktop format (`.one` files created by Microsoft OneNote 2010).",
        "OneNoteOnline": "OneNote Online format used by the web-based OneNote application.",
        "OneNote2007": "OneNote 2007 desktop format (`.one` files created by Microsoft OneNote 2007).",
    },
    "HorizontalAlignment.md": {
        "Left": "Aligns content to the left edge of the container.",
        "Center": "Centers content horizontally within the container.",
        "Right": "Aligns content to the right edge of the container.",
    },
    "NodeType.md": {
        "Document": "The root `Document` node of a OneNote notebook.",
        "Page": "A `Page` node representing a single page within a section.",
        "Outline": "An `Outline` container grouping one or more `OutlineElement` nodes.",
        "OutlineElement": "An `OutlineElement` node holding content items such as text or images.",
        "RichText": "A `RichText` node containing formatted text content.",
        "Image": "An `Image` node representing an embedded or attached picture.",
        "Table": "A `Table` node containing rows and cells.",
        "AttachedFile": "An `AttachedFile` node representing a file attachment embedded in a page.",
    },
}


def fix_enum_descriptions(content, descriptions):
    """Fill in empty enum value description cells."""
    for member, desc in descriptions.items():
        # Match: | `Member` | | or | `Member` |  |
        pattern = rf'(\|\s*`{re.escape(member)}`\s*\|\s*)(\|)'
        replacement = rf'\g<1>{desc} |'
        content = re.sub(pattern, replacement, content)
    return content


changed = 0
for fname, upd in UPDATES.items():
    path = REF / fname
    if not path.exists():
        print(f"  SKIP (not found): {fname}")
        continue
    content = path.read_text(encoding="utf-8")
    old = upd["old"]
    new = upd["new"]
    if old not in content:
        print(f"  MISMATCH (old not found): {fname}")
        # Show what's there
        lines = content.split("\n")
        for i, line in enumerate(lines[:45]):
            print(f"    {i+1}: {repr(line)}")
        continue
    content = content.replace(old, new, 1)
    if fname in ENUM_DESCRIPTIONS:
        content = fix_enum_descriptions(content, ENUM_DESCRIPTIONS[fname])
    path.write_text(content, encoding="utf-8")
    changed += 1
    print(f"  UPDATED: {fname}")

print(f"\nTotal updated: {changed}")
