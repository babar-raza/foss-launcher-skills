"""Fix remaining email/net FAIL items: near-stub pages + property-type-code + sector-marker."""
import re
from pathlib import Path

# Fix 1: Reference pages just a few words short — add extra sentence to overview
REF = Path("content/reference.aspose.org/en/email/net")
KB = Path("content/kb.aspose.org/en/email/net")

EXTRA_SENTENCES = {
    # reference pages
    "common-message-property-id.md": (
        "Base type: `ushort`.",
        "Base type: `ushort`. Use these constants instead of raw hex literals to make message-handling code self-documenting and resistant to accidental transposition errors.",
    ),
    "directory-entry.md": (
        "Use `DirectoryEntry` as a common type when iterating the directory tree returned by `CfbReader`.",
        "Use `DirectoryEntry` as a common type when iterating the directory tree returned by `CfbReader`. Pair it with `CfbReader.GetStreamData` to read stream content by stream ID.",
    ),
    "msg-document.md": (
        "Call `ToCfbDocument` to convert the MSG document back to a raw `CfbDocument` for low-level inspection or re-serialization with `CfbWriter`.",
        "Call `ToCfbDocument` to convert the MSG document back to a raw `CfbDocument` for low-level inspection or re-serialization with `CfbWriter`. The `Strict` flag controls whether structural validation errors are raised or silently recorded.",
    ),
    "msg-storage.md": (
        "Use `AddStream` and `AddStorage` to construct a document tree, and `FindStream`/`FindStorage` to locate named children when reading.",
        "Use `AddStream` and `AddStorage` to construct a document tree, and `FindStream`/`FindStorage` to locate named children when reading. Pass the completed root `MsgStorage` to `MsgWriter` to serialize the full document.",
    ),
    # property-type-code and sector-marker need full overview replacement
}

FULL_OVERRIDES = {
    "property-type-code.md": {
        "old": "MAPI property type codes that appear in property tags and stream names in MSG files.\n\n`PropertyTypeCode` is an enum in Aspose.Email FOSS for .NET (base type: `ushort`).",
        "new": "`PropertyTypeCode` is an enumeration of MAPI property type codes (the low 16 bits of a MAPI property tag). Each value identifies the data type of a property's stored value: integer, floating-point, boolean, string, binary, time, GUID, or a multi-value variant of those types. Use these constants with `MapiProperty.PropertyType` and `MapiPropertyCollection` to decode or construct MAPI property streams in `.msg` files.\n\nBase type: `ushort`.",
        "member_descs": {
            "PtypInteger16": "16-bit signed integer property (`PT_I2`, type code `0x0002`).",
            "PtypInteger32": "32-bit signed integer property (`PT_LONG`, type code `0x0003`).",
            "PtypFloating32": "32-bit IEEE 754 floating-point value (`PT_R4`, type code `0x0004`).",
            "PtypFloating64": "64-bit IEEE 754 double-precision value (`PT_DOUBLE`, type code `0x0005`).",
            "PtypCurrency": "64-bit signed integer scaled by 10,000 representing a currency amount (`PT_CURRENCY`, type code `0x0006`).",
            "PtypFloatingTime": "OLE floating-point date-time value as a `double` (`PT_APPTIME`, type code `0x0007`).",
            "PtypErrorCode": "32-bit HRESULT error code (`PT_ERROR`, type code `0x000A`).",
            "PtypBoolean": "16-bit Boolean: 0 = false, non-zero = true (`PT_BOOLEAN`, type code `0x000B`).",
            "PtypObject": "Embedded IStream or IStorage object (`PT_OBJECT`, type code `0x000D`).",
            "PtypInteger64": "64-bit signed integer (`PT_I8`, type code `0x0014`).",
            "PtypString8": "Null-terminated 8-bit ANSI/MBCS string (`PT_STRING8`, type code `0x001E`).",
            "PtypString": "Null-terminated UTF-16LE Unicode string (`PT_UNICODE`, type code `0x001F`).",
            "PtypTime": "64-bit FILETIME UTC date-time value (`PT_SYSTIME`, type code `0x0040`).",
            "PtypGuid": "128-bit GUID / UUID value (`PT_CLSID`, type code `0x0048`).",
            "PtypBinary": "Variable-length byte array with a 32-bit length prefix (`PT_BINARY`, type code `0x0102`).",
            "PtypMultipleInteger16": "Multi-value array of 16-bit integers (`PT_MV_I2`, type code `0x1002`).",
            "PtypMultipleInteger32": "Multi-value array of 32-bit integers (`PT_MV_LONG`, type code `0x1003`).",
            "PtypMultipleFloating32": "Multi-value array of 32-bit floats (`PT_MV_R4`, type code `0x1004`).",
            "PtypMultipleFloating64": "Multi-value array of 64-bit doubles (`PT_MV_DOUBLE`, type code `0x1005`).",
            "PtypMultipleCurrency": "Multi-value array of currency values (`PT_MV_CURRENCY`, type code `0x1006`).",
            "PtypMultipleFloatingTime": "Multi-value array of OLE date-time values (`PT_MV_APPTIME`, type code `0x1007`).",
            "PtypMultipleInteger64": "Multi-value array of 64-bit integers (`PT_MV_I8`, type code `0x1014`).",
            "PtypMultipleString8": "Multi-value array of ANSI strings (`PT_MV_STRING8`, type code `0x101E`).",
            "PtypMultipleString": "Multi-value array of Unicode strings (`PT_MV_UNICODE`, type code `0x101F`).",
            "PtypMultipleTime": "Multi-value array of FILETIME values (`PT_MV_SYSTIME`, type code `0x1040`).",
            "PtypMultipleGuid": "Multi-value array of GUIDs (`PT_MV_CLSID`, type code `0x1048`).",
            "PtypMultipleBinary": "Multi-value array of binary blobs (`PT_MV_BINARY`, type code `0x1102`).",
        },
    },
    "sector-marker.md": {
        "old": "Special FAT marker values reserved for sector allocation metadata.\n\n`SectorMarker` is an enum in Aspose.Email FOSS for .NET (base type: `uint`).",
        "new": "`SectorMarker` is an enumeration of the reserved 32-bit values used in the FAT and mini-FAT sector chains of a Compound File Binary document. When iterating a sector chain in `CfbReader.Fat`, you will encounter these terminal markers to identify chain boundaries, free sectors, FAT meta-sectors, and DIFAT meta-sectors. Compare against these enum values instead of hard-coding raw unsigned hex literals.\n\nBase type: `uint`.",
        "member_descs": {
            "DIFSECT": "DIFAT sector marker (`0xFFFFFFFC`): this FAT entry describes a DIFAT meta-sector.",
            "FATSECT": "FAT sector marker (`0xFFFFFFFD`): this FAT entry describes a FAT meta-sector.",
            "ENDOFCHAIN": "End-of-chain marker (`0xFFFFFFFE`): this sector is the last in a chain.",
            "FREESECT": "Free sector marker (`0xFFFFFFFF`): this sector is unallocated.",
        },
    },
}

# KB pages: just extend the intro paragraph with a few more words
KB_EXTENSIONS = {
    "how-to-read-msg-files-net.md": (
        "This guide shows how to open an Outlook `.msg` file and extract its contents using\nAspose.Email FOSS for .NET.",
        "This guide shows how to open an Outlook `.msg` file and extract its contents using\nAspose.Email FOSS for .NET. You will access the subject, body, sender, recipients, and attachment list using `MapiMessage`.",
    ),
    "how-to-convert-eml-to-msg-net.md": (
        "This guide shows how to convert between EML (RFC 5322 / MIME) and Outlook MSG formats\nusing Aspose.Email FOSS for .NET.",
        "This guide shows how to convert between EML (RFC 5322 / MIME) and Outlook MSG formats\nusing Aspose.Email FOSS for .NET. Both directions are covered: `LoadFromEml` to import EML and `SaveToEml` to export to EML.",
    ),
}


def fill_enum_descs(content, descs):
    """Fill in empty description cells for enum/method members."""
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if line.strip().startswith('|') and '|' in line:
            # Check if this is a table data row with an empty last cell
            parts = line.rstrip().split('|')
            # Find if any member name from descs matches
            for member_name, desc in descs.items():
                if member_name in line:
                    # Check if last cell is empty
                    stripped = line.rstrip()
                    if re.search(r'\|\s*$', stripped):
                        before_last = stripped.rstrip('|').rstrip()
                        if before_last.endswith('|') or re.search(r'\|\s*$', before_last):
                            line = before_last.rstrip('|').rstrip() + '| ' + desc + ' |'
                    break
        new_lines.append(line)
    return '\n'.join(new_lines)


changed = 0

# Fix extra-sentence pages
for fname, (old, new) in EXTRA_SENTENCES.items():
    path = REF / fname
    if not path.exists():
        print(f'  NOT FOUND: {fname}')
        continue
    content = path.read_text(encoding='utf-8')
    if old not in content:
        print(f'  MISMATCH: {fname}')
        continue
    content = content.replace(old, new, 1)
    path.write_text(content, encoding='utf-8')
    changed += 1
    print(f'  UPDATED: {fname}')

# Fix full override pages
for fname, upd in FULL_OVERRIDES.items():
    path = REF / fname
    if not path.exists():
        print(f'  NOT FOUND: {fname}')
        continue
    content = path.read_text(encoding='utf-8')
    old = upd['old']
    new = upd['new']
    if old not in content:
        print(f'  MISMATCH (overview): {fname}')
        continue
    content = content.replace(old, new, 1)
    if 'member_descs' in upd:
        content = fill_enum_descs(content, upd['member_descs'])
    path.write_text(content, encoding='utf-8')
    changed += 1
    print(f'  UPDATED: {fname}')

# Fix KB pages
for fname, (old, new) in KB_EXTENSIONS.items():
    path = KB / fname
    if not path.exists():
        print(f'  NOT FOUND: {fname}')
        continue
    content = path.read_text(encoding='utf-8')
    if old not in content:
        print(f'  MISMATCH: {fname}')
        continue
    content = content.replace(old, new, 1)
    path.write_text(content, encoding='utf-8')
    changed += 1
    print(f'  UPDATED: {fname} (KB)')

print(f'\nTotal updated: {changed}')
