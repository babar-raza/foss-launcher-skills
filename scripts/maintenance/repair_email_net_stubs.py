"""Fix email/net reference stub pages: add prose overviews and member descriptions."""
import re
from pathlib import Path

REF = Path("content/reference.aspose.org/en/email/net")

# Map: filename_stem → (old_overview_line, new_overview_block)
OVERVIEWS = {
    "cfb-constants": {
        "old": "`CfbConstants` is a class in Aspose.Email FOSS for .NET.",
        "new": "`CfbConstants` is a static class that exposes the numeric constants defined by the Compound File Binary (CFB) specification (MS-CFB). Use these constants when parsing raw sector chains, directory entry fields, and stream-size limits. The values match the byte-order mark, reserved sector IDs, and size thresholds described in the official specification. No instantiation is required; access all members through the class name.",
    },
    "cfb-document": {
        "old": "`CfbDocument` is a class in Aspose.Email FOSS for .NET.",
        "new": "`CfbDocument` represents an in-memory Compound File Binary document. Use the static factory methods `FromFile`, `FromStream`, or `FromReader` to open an existing CFB file, or call the full constructor to create a new document from a `CfbStorage` root. The `Root` property gives access to the top-level storage, from which you can navigate the entire directory tree.",
    },
    "cfb-exception": {
        "old": "`CfbException` is a class in Aspose.Email FOSS for .NET.  \nInherits from: `Exception`.",
        "new": "`CfbException` is the exception type raised by the CFB reader and writer when a Compound File Binary document is malformed, truncated, or violates the MS-CFB specification. It inherits from the .NET base `Exception` class. Catch `CfbException` around calls to `CfbReader`, `CfbDocument`, and `CfbWriter` to recover from format errors without crashing.",
    },
    "cfb-node": {
        "old": "`CfbNode` is a class in Aspose.Email FOSS for .NET.",
        "new": "`CfbNode` is the base class for all Compound File Binary directory entries — both storage containers (`CfbStorage`) and data streams (`CfbStream`). It exposes the metadata fields common to every 128-byte CFB directory entry: `Name`, `Clsid`, `StateBits`, `CreationTime`, and `ModifiedTime`. Use `CfbNode` as a common type when iterating the directory tree returned by `CfbReader`.",
    },
    "cfb-reader": {
        "old": "`CfbReader` is a class in Aspose.Email FOSS for .NET.  \nInherits from: `IDisposable`.",
        "new": "`CfbReader` is a low-level, read-only parser for Compound File Binary files. Construct it via `FromFile` or `FromStream`, then navigate the directory tree with `IterStorages`, `IterStreams`, `IterChildren`, and `FindChildByName`. Use `GetStreamData` to read raw bytes from a named stream. Implements `IDisposable`; always use it inside a `using` block to release file handles.",
    },
    "cfb-storage": {
        "old": "`CfbStorage` is a class in Aspose.Email FOSS for .NET.  \nInherits from: `CfbNode`.",
        "new": "`CfbStorage` is a CFB directory entry that acts as a container node, analogous to a folder in a file system. It inherits from `CfbNode` and adds the `Children` collection, which holds subordinate `CfbNode` entries (other storages or streams). Use `AddStorage` and `AddStream` to build a document tree before passing it to `CfbWriter`.",
    },
    "cfb-stream": {
        "old": "`CfbStream` is a class in Aspose.Email FOSS for .NET.  \nInherits from: `CfbNode`.",
        "new": "`CfbStream` is a CFB directory entry that holds raw binary data, analogous to a file. It inherits from `CfbNode` and adds the `Data` property which stores the stream content as a byte array. Create a `CfbStream` with a name and optional data, then add it to a `CfbStorage` before serializing the document with `CfbWriter`.",
    },
    "cfb-writer": {
        "old": "`CfbWriter` is a class in Aspose.Email FOSS for .NET.",
        "new": "`CfbWriter` serializes a `CfbDocument` into a valid Compound File Binary file. Call `ToBytes` to obtain the serialized content as a byte array, or `WriteFile` to write directly to disk. The internal `Serialize` method builds the FAT, DIFAT, mini-FAT, and directory sectors according to the MS-CFB specification. Constructors are used internally by the writer to represent entry records and sector chains.",
    },
    "common-message-property-id": {
        "old": "Common MAPI property identifiers used by the MSG reader and writer for core message semantics, body fields, transport headers, and attachments.\n\n`CommonMessagePropertyId` is an enum in Aspose.Email FOSS for .NET (base type: `ushort`).",
        "new": "`CommonMessagePropertyId` is an enumeration of the MAPI property identifiers most commonly used when reading and writing `.msg` files. Each value corresponds to the low 16 bits of a MAPI property tag. Use these constants with `MapiMessage.SetProperty`, `MapiMessage.GetPropertyValue`, and `MapiPropertyCollection` to avoid hard-coding raw hex property IDs.\n\nBase type: `ushort`.",
    },
    "directory-color-flag": {
        "old": "Stores the red-black tree color used by directory sibling links.\n\n`DirectoryColorFlag` is an enum in Aspose.Email FOSS for .NET (base type: `byte`).",
        "new": "`DirectoryColorFlag` is an enumeration encoding the red-black tree color byte stored in every CFB directory entry. The CFB specification (MS-CFB §2.6.2) uses a red-black tree to maintain the sibling ordering of directory entries within a storage. Reading this value from a `DirectoryEntry` or `CfbWriter.EntryRecord` identifies whether the node is a red or black node in the tree.\n\nBase type: `byte`.",
    },
    "directory-entry": {
        "old": "`DirectoryEntry` is a class in Aspose.Email FOSS for .NET.",
        "new": "`DirectoryEntry` represents a single 128-byte directory entry record parsed from the CFB directory sector by `CfbReader`. Iterate the raw entries via `CfbReader.DirectoryEntries`. Call `IsStorage()`, `IsStream()`, or `IsRoot()` to determine the entry type without inspecting the raw object-type byte. Use the companion `DirectoryObjectType` enum for explicit type comparisons.",
    },
    "directory-entry-name-comparer": {
        "old": "`DirectoryEntryNameComparer` is a class in Aspose.Email FOSS for .NET.",
        "new": "`DirectoryEntryNameComparer` implements `IComparer<string>` for CFB directory entry names using the UTF-16LE, case-insensitive comparison algorithm defined in MS-CFB §2.6.4. Use it to locate children in the red-black tree of a CFB storage, or when building a sorted directory manually before passing it to `CfbWriter`. The `Compare` method returns a negative, zero, or positive integer following the standard `IComparer` contract.",
    },
    "directory-object-type": {
        "old": "Classifies the directory entry payload as unallocated, storage, stream, or root storage.\n\n`DirectoryObjectType` is an enum in Aspose.Email FOSS for .NET (base type: `byte`).",
        "new": "`DirectoryObjectType` is an enumeration identifying the object type byte of a CFB directory entry. The CFB specification stores a single byte at offset 66 of each 128-byte entry record to indicate whether the entry is a storage container, a data stream, the root storage, or unallocated. Use the enum constants instead of raw byte literals when inspecting `CfbWriter.ObjectType` or building directory entries programmatically.\n\nBase type: `byte`.",
    },
    "header": {
        "old": "`Header` is a class in Aspose.Email FOSS for .NET.",
        "new": "`Header` exposes the two sector-size fields parsed from the 512-byte CFB file header by `CfbReader`. `SectorSize` is derived from the sector size power field (typically 512 bytes for v3 or 4096 bytes for v4 CFB files). `MiniSectorSize` is the mini-sector size (always 64 bytes per the specification). Access a `Header` instance via `CfbReader.Header` after opening a file.",
    },
    "mapi-attachment": {
        "old": "`MapiAttachment` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MapiAttachment` represents a file or embedded-message attachment in a MAPI `.msg` email. Create attachments using the static factory methods `FromBytes` or `FromStream`, then add them to a `MapiMessage` via `AddAttachment`. Read the attachment content via `LoadData` or `OpenRead`. The `Properties` collection exposes low-level MAPI property streams for the attachment storage.",
    },
    "mapi-message": {
        "old": "`MapiMessage` is a class in Aspose.Email FOSS for .NET.  \nInherits from: `IDisposable`.",
        "new": "`MapiMessage` is the primary class for reading and writing `.msg` email files in the Aspose.Email FOSS library. Load an existing message with `FromFile`, `FromStream`, or one of the `LoadFromEml` overloads. Build a new message with `Create`, then call `AddRecipient` and `AddAttachment`. Save back to `.msg` with `Save`, or export to EML with `SaveToEml`. Implements `IDisposable`; use a `using` block to ensure resources are released.",
    },
    "mapi-property": {
        "old": "`MapiProperty` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MapiProperty` represents a single MAPI property entry: a combination of a 16-bit property ID, a 16-bit property type code, a value, and optional flags. The `PropertyTag` combines the property ID and type into a 32-bit MAPI tag. Use `MapiPropertyCollection.Get` to retrieve a property by ID and type, or `MapiMessage.SetProperty` to set one.",
    },
    "mapi-property-collection": {
        "old": "`MapiPropertyCollection` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MapiPropertyCollection` is a keyed collection of `MapiProperty` objects indexed by property ID and type code. Use `Set` to add-or-replace a property, `Add` to construct and insert a new one, `Get` to retrieve an existing entry, `Remove` to delete it, and `IterProperties` to enumerate all stored properties. Accessible via `MapiMessage.Properties`, `MapiAttachment.Properties`, and `MapiRecipient.Properties`.",
    },
    "mapi-recipient": {
        "old": "`MapiRecipient` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MapiRecipient` represents a single addressee in a MAPI message: a To, Cc, or Bcc recipient. Read the recipient's display name via `DisplayName`, email address via `EmailAddress`, address type via `AddressType` (e.g. `SMTP`), and recipient type via `RecipientType` (1 = To, 2 = Cc, 3 = Bcc). The `Properties` collection exposes additional MAPI property data stored in the recipient sub-storage.",
    },
    "msg-constants": {
        "old": "`MsgConstants` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MsgConstants` is a static class exposing string and numeric constants that describe the layout of a `.msg` Compound File Binary document. These include storage name prefixes for attachments and recipients, the embedded-message storage name, named-property mapping storage name, and maximum counts for attachment and recipient storages per message. No instantiation is required; access all members through the class name.",
    },
    "msg-document": {
        "old": "`MsgDocument` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MsgDocument` represents a parsed `.msg` file as a tree of `MsgStorage` nodes. Load an existing file with `FromFile` or `FromStream`, then navigate `Root.Storages` and `Root.Streams` to access the MAPI data. Call `ToCfbDocument` to convert the MSG document back to a raw `CfbDocument` for low-level inspection or re-serialization with `CfbWriter`.",
    },
    "msg-exception": {
        "old": "`MsgException` is a class in Aspose.Email FOSS for .NET.  \nInherits from: `Exception`.",
        "new": "`MsgException` is raised when a `.msg` file violates the expected MAPI storage structure — for example when a required root storage entry is missing or a property stream is corrupt. It inherits from the .NET base `Exception` class. Catch `MsgException` around `MsgReader`, `MsgDocument`, and `MsgWriter` operations to handle format-level errors separately from I/O failures.",
    },
    "msg-reader": {
        "old": "`MsgReader` is a class in Aspose.Email FOSS for .NET.  \nInherits from: `IDisposable`.",
        "new": "`MsgReader` is a high-level reader for `.msg` email files that validates the MAPI storage structure and reports inconsistencies via `ValidationIssues`. Construct it with `FromFile` or `FromStream`, inspect `ValidationIssues` for any detected structural problems, then pass the result to `MapiMessage.FromMsgDocument` or use it directly to access the parsed document tree. Implements `IDisposable`.",
    },
    "msg-storage": {
        "old": "`MsgStorage` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MsgStorage` is a named storage node within a `.msg` document tree with a semantic `Role` (message, recipient, attachment, or embedded message). It holds child `MsgStream` property streams and child `MsgStorage` sub-storages. Use `AddStream` and `AddStorage` to construct a document tree, and `FindStream`/`FindStorage` to locate named children when reading.",
    },
    "msg-storage-role": {
        "old": "`MsgStorageRole` is an enum in Aspose.Email FOSS for .NET.",
        "new": "`MsgStorageRole` is an enumeration identifying the semantic purpose of a `MsgStorage` node within a `.msg` document. Each constant maps to a well-known MAPI sub-storage naming pattern: `Message` is the root message storage, `Recipient` is a `__recip_version1.0_#XXXXXXXX` storage, `Attachment` is an `__attach_version1.0_#XXXXXXXX` storage, and `EmbeddedMessage` is an attachment whose content is another `.msg` file.",
    },
    "msg-stream": {
        "old": "`MsgStream` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MsgStream` is a named binary stream node within a `MsgStorage`. Each stream stores the raw bytes for a single MAPI property — for example the property value stream `__substg1.0_0037001F` holds the Unicode subject text. Read the raw bytes via `Data`, and check `Name` to identify which MAPI property tag the stream encodes. Use `CreationTime` and `ModifiedTime` for CFB-level timestamping.",
    },
    "msg-writer": {
        "old": "`MsgWriter` is a class in Aspose.Email FOSS for .NET.",
        "new": "`MsgWriter` serializes a `MsgDocument` into a valid `.msg` file. Call `ToBytes` to obtain the serialized content as a byte array for in-memory use, or call `WriteFile` to write directly to a file path. The writer internally builds a `CfbDocument` from the `MsgDocument` tree and delegates the binary serialization to `CfbWriter`.",
    },
}

# Per-page member descriptions: {filename_stem: {member_name: description}}
MEMBER_DESCS = {
    "cfb-document": {
        # Methods
        "FromReader": "Creates a `CfbDocument` by reading all entries from an open `CfbReader` instance.",
        "FromFile": "Opens the CFB file at `path` and returns a new `CfbDocument`.",
        "FromStream": "Reads a CFB document from `stream` and returns a new `CfbDocument`.",
        # Properties
        "Root": "The root `CfbStorage` entry at stream ID 0; the starting point for all directory traversal.",
        "MajorVersion": "CFB major version from the file header (3 for 512-byte sectors, 4 for 4096-byte sectors).",
        "MinorVersion": "CFB minor version from the file header (always 0x003E per the specification).",
        "TransactionSignatureNumber": "Transaction signature field from the CFB header; non-zero only in transacted files.",
    },
    "cfb-node": {
        "Name": "UTF-16LE name of the directory entry as stored in the CFB directory sector.",
        "Clsid": "16-byte CLSID stored in the directory entry; all zeros for entries that have no associated class.",
        "StateBits": "User-defined state bits field of the directory entry; semantics are application-specific.",
        "CreationTime": "Directory-entry creation timestamp as a 64-bit FILETIME value (100-ns intervals since 1601-01-01 UTC).",
        "ModifiedTime": "Directory-entry last-modification timestamp as a 64-bit FILETIME value.",
    },
    "cfb-reader": {
        # Methods
        "FromFile": "Opens the CFB file at `path` and returns a new `CfbReader`.",
        "FromStream": "Reads a CFB file from `stream` and returns a new `CfbReader`.",
        "Dispose": "Releases any file handle or stream held by this reader.",
        "GetEntry": "Returns the `DirectoryEntry` for the given `streamId`.",
        "GetStreamData": "Returns the raw byte content of the stream identified by `streamId`.",
        "IterStorages": "Yields all storage-type directory entries in tree order.",
        "IterStreams": "Yields all stream-type directory entries in tree order.",
        "IterChildren": "Yields direct child entries of the storage identified by `storageStreamId`.",
        "IterTree": "Yields all entries in the subtree rooted at `startStreamId` (depth-first).",
        "FindChildByName": "Returns the stream ID of the direct child of `storageStreamId` whose name equals `name`, or null if not found.",
        "ResolvePath": "Walks a sequence of `names` starting from `startStreamId` and returns the stream ID of the final entry.",
        # Properties
        "Header": "The parsed CFB file header; exposes sector-size fields.",
        "Difat": "Read-only view of the DIFAT sector chain.",
        "Fat": "Read-only view of the FAT (file allocation table) sector chain.",
        "MiniFat": "Read-only view of the mini-FAT sector chain used for streams smaller than `MiniStreamCutoffSize`.",
        "DirectoryEntries": "All 128-byte directory entries parsed from the directory sectors, in raw order.",
        "RootEntry": "The root directory entry (stream ID 0).",
        "MiniStream": "Raw bytes of the mini-stream container (the data stream of the root entry).",
        "MajorVersion": "CFB major version parsed from the file header.",
        "SectorSize": "Sector size in bytes (512 for v3, 4096 for v4).",
        "MiniSectorSize": "Mini-sector size in bytes (always 64).",
        "DirectoryEntryCount": "Total number of directory entry records in the directory sectors.",
        "MaterializedStreamCount": "Number of streams with non-empty data in the parsed document.",
        "FileSize": "Total size of the source file or stream in bytes.",
    },
    "cfb-storage": {
        # Methods
        "AddStorage": "Adds a child `CfbStorage` to this storage node.",
        "AddStream": "Adds a child `CfbStream` to this storage node.",
        # Properties
        "Children": "Ordered list of child `CfbNode` entries (storages and streams) directly under this storage.",
    },
    "cfb-stream": {
        # Properties
        "Data": "Raw byte content of this CFB stream entry.",
    },
    "cfb-writer": {
        # Methods
        "ToBytes": "Serializes `document` to a CFB-compliant byte array.",
        "WriteFile": "Serializes `document` and writes it to the file at `path`.",
        "Serialize": "Performs the internal CFB layout: allocates FAT sectors, builds directory entries, and returns the complete binary.",
        # Properties
        "StreamId": "Zero-based directory index assigned to this entry record.",
        "Name": "UTF-16LE entry name as it will appear in the CFB directory.",
        "ObjectType": "The `DirectoryObjectType` value encoded in this entry's object-type byte.",
        "Clsid": "16-byte CLSID written to this entry's CLSID field.",
        "StateBits": "Application-defined state bits written to this entry.",
        "CreationTime": "Creation timestamp (FILETIME) written to this entry.",
        "ModifiedTime": "Modification timestamp (FILETIME) written to this entry.",
        "StreamData": "Payload bytes for stream-type entries (empty for storage-type entries).",
        "Children": "Ordered list of child `EntryRecord` entries for storage-type nodes.",
        "ColorFlag": "Red-black tree color written to this entry's directory record.",
        "LeftSiblingId": "Stream ID of the left sibling in the red-black tree.",
        "RightSiblingId": "Stream ID of the right sibling in the red-black tree.",
        "ChildId": "Stream ID of the first child entry (for storage-type nodes).",
        "StartingSectorLocation": "First FAT sector index for this stream's data.",
        "StreamSize": "Size in bytes of the stream's data payload.",
        "IsRoot": "True if this entry is the root storage entry (stream ID 0).",
        "IsStorage": "True if this entry is a storage container.",
        "IsStream": "True if this entry is a data stream.",
        "Payload": "The complete serialized bytes of this entry (used internally by the chain builder).",
        "Sectors": "Ordered list of FAT sector indices allocated to this entry's data.",
        "FirstSector": "Index of the first FAT sector allocated to this entry's data.",
    },
    "common-message-property-id": {
        "MessageClass": "PR_MESSAGE_CLASS (0x001A): message type identifier string (e.g. `IPM.Note`).",
        "TransportMessageHeaders": "PR_TRANSPORT_MESSAGE_HEADERS (0x007D): raw RFC 2822 Internet message headers.",
        "Subject": "PR_SUBJECT (0x0037): message subject line.",
        "DisplayTo": "PR_DISPLAY_TO (0x0E04): comma-separated display names of To recipients.",
        "DisplayCc": "PR_DISPLAY_CC (0x0E03): comma-separated display names of Cc recipients.",
        "DisplayBcc": "PR_DISPLAY_BCC (0x0E02): comma-separated display names of Bcc recipients.",
        "InternetMessageId": "PR_INTERNET_MESSAGE_ID (0x1035): RFC 2822 Message-ID header value.",
        "MessageFlags": "PR_MESSAGE_FLAGS (0x0E07): bitmask of message status flags (read, unsent, submitted, etc.).",
        "InternetCodepage": "PR_INTERNET_CODEPAGE (0x3FDE): ANSI code page for 8-bit string encoding.",
        "SenderName": "PR_SENDER_NAME (0x0C1A): display name of the message sender.",
        "SenderAddressType": "PR_SENDER_ADDRTYPE (0x0C1E): address type of the sender (e.g. `SMTP`).",
        "SenderEmailAddress": "PR_SENDER_EMAIL_ADDRESS (0x0C1F): SMTP address of the sender.",
        "MessageDeliveryTime": "PR_MESSAGE_DELIVERY_TIME (0x0E06): UTC delivery timestamp as a FILETIME.",
        "StoreSupportMask": "PR_STORE_SUPPORT_MASK (0x340D): capabilities bitmask of the message store.",
        "Body": "PR_BODY (0x1000): plain-text message body.",
        "BodyHtml": "PR_HTML (0x1013): HTML message body as a byte stream.",
        "DisplayName": "PR_DISPLAY_NAME (0x3001): display name (used for recipients and attachments).",
        "AttachMethod": "PR_ATTACH_METHOD (0x3705): attachment method (ATTACH_BY_VALUE, ATTACH_EMBEDDED_MSG, etc.).",
        "AttachDataBinary": "PR_ATTACH_DATA_BIN (0x3701): raw attachment binary data.",
        "AttachFilename": "PR_ATTACH_FILENAME (0x3704): short (8.3) attachment filename.",
        "AttachLongFilename": "PR_ATTACH_LONG_FILENAME (0x3707): full long filename for the attachment.",
        "AttachMimeTag": "PR_ATTACH_MIME_TAG (0x370E): MIME content-type of the attachment.",
        "AttachContentId": "PR_ATTACH_CONTENT_ID (0x3712): Content-ID header for inline attachments.",
        "ScheduleInfoDelegateNames": "PR_SCHDINFO_DELEGATE_NAMES (0x6844): delegate display names for calendar scheduling.",
        "ScheduleInfoMonthsBusy": "PR_SCHDINFO_MONTHS_BUSY (0x6851): months with busy-time data in calendar scheduling info.",
    },
    "directory-color-flag": {
        "Red": "Red node in the CFB directory red-black tree.",
        "Black": "Black node in the CFB directory red-black tree.",
    },
    "directory-entry": {
        "IsStorage": "Returns `true` if this entry's object-type byte is `StorageObject` (0x01).",
        "IsStream": "Returns `true` if this entry's object-type byte is `StreamObject` (0x02).",
        "IsRoot": "Returns `true` if this entry's object-type byte is `RootStorageObject` (0x05).",
    },
    "directory-entry-name-comparer": {
        "Compare": "Compares two CFB directory entry names using UTF-16LE, case-insensitive collation per MS-CFB §2.6.4.",
    },
    "directory-object-type": {
        "UnknownOrUnallocated": "Unallocated or unused directory entry (object-type byte `0x00`).",
        "StorageObject": "Storage container entry, analogous to a directory (object-type byte `0x01`).",
        "StreamObject": "Data stream entry, analogous to a file (object-type byte `0x02`).",
        "RootStorageObject": "Root storage entry; exactly one per CFB document (object-type byte `0x05`).",
    },
    "header": {
        "SectorSize": "Sector size in bytes derived from the sector-size-power field; 512 bytes for CFB v3 files.",
        "MiniSectorSize": "Mini-sector size in bytes; always 64 per the CFB specification.",
    },
    "mapi-attachment": {
        # Methods
        "FromBytes": "Creates a `MapiAttachment` from a byte array with optional MIME type and Content-ID.",
        "FromStream": "Creates a `MapiAttachment` by reading all bytes from `stream`.",
        "LoadData": "Loads attachment binary data from `stream` into `Data`.",
        "OpenRead": "Returns a `Stream` positioned at the start of the attachment data for sequential reading.",
        # Properties
        "Filename": "Original filename of the attached file, or `null` if not set.",
        "Data": "Raw binary content of the attachment.",
        "MimeType": "MIME content-type string (e.g. `application/pdf`), or `null` if not specified.",
        "ContentId": "Content-ID header value for inline MIME attachments, or `null` if not set.",
        "EmbeddedMessage": "The embedded `MapiMessage` when `IsEmbeddedMessage` is `true`; otherwise `null`.",
        "Properties": "Low-level MAPI property collection for this attachment's storage.",
        "IsEmbeddedMessage": "True if the attachment stores an embedded `.msg` message rather than raw file data.",
        "IsStorageAttachment": "True if the attachment is stored as a sub-storage in the CFB document rather than a stream.",
    },
    "mapi-message": {
        # Methods
        "Create": "Creates a new `MapiMessage` with the given subject and body, optionally using Unicode strings.",
        "FromFile": "Loads a `MapiMessage` from a `.msg` file at `path`; `strict` enables full structural validation.",
        "FromStream": "Loads a `MapiMessage` from `stream`; `strict` enables full structural validation.",
        "FromMsgDocument": "Wraps an already-parsed `MsgDocument` in a `MapiMessage`.",
        "LoadFromEml": "Converts an EML file at `path` to a `MapiMessage` via in-memory MIME parsing.",
        "Dispose": "Releases unmanaged resources held by this message.",
        "AddRecipient": "Adds a recipient with the given email address, display name, and type (1 = To, 2 = Cc, 3 = Bcc).",
        "AddAttachment": "Attaches a file by name and binary data, optionally specifying MIME type and Content-ID.",
        "AddEmbeddedMessageAttachment": "Attaches another `MapiMessage` as an embedded-message attachment.",
        "SetProperty": "Sets a raw MAPI property by property ID, type, value, and flags.",
        "GetPropertyValue": "Retrieves the value of a MAPI property by ID and optional type; `decode` controls string decoding.",
        "IterPropertyKeys": "Enumerates the (propertyId, propertyType) key pairs of all stored properties.",
        "IterProperties": "Enumerates all `MapiProperty` objects stored in this message.",
        "IterAttachmentsInfo": "Enumerates attachment metadata without loading full attachment data.",
        "ToMsgDocument": "Converts this `MapiMessage` to a `MsgDocument` suitable for CFB serialization.",
        "Save": "Saves the message in-place (for messages originally loaded from a file or stream).",
        "SaveToEml": "Exports the message to an EML byte array.",
        # Properties (only filling the empty ones — 3 already have descriptions)
        "UnicodeStrings": "True if string properties are stored as Unicode (PT_UNICODE); false for ANSI (PT_STRING8).",
        "Properties": "Top-level MAPI property collection for this message.",
        "Recipients": "Ordered list of `MapiRecipient` entries for To, Cc, and Bcc addresses.",
        "Attachments": "Ordered list of `MapiAttachment` entries.",
        "MajorVersion": "CFB major version from the underlying compound file header.",
        "MinorVersion": "CFB minor version from the underlying compound file header.",
        "TransactionSignatureNumber": "CFB transaction signature number from the file header.",
        "ValidationIssues": "List of structural validation issues detected when `strict` mode was enabled.",
        "Subject": "Message subject string, or `null` if not set.",
        "Body": "Plain-text message body, or `null` if not set.",
        "HtmlBody": "HTML message body, or `null` if not set.",
        "MessageClass": "MAPI message class string (e.g. `IPM.Note`), or `null` if not set.",
        "SenderName": "Sender display name, or `null` if not set.",
        "SenderEmailAddress": "Sender SMTP email address, or `null` if not set.",
        "SenderAddressType": "Sender address type string (e.g. `SMTP`), or `null` if not set.",
        "InternetMessageId": "RFC 2822 Message-ID value, or `null` if not set.",
        "MessageDeliveryTime": "Delivery timestamp as `DateTime?`, or `null` if not set.",
    },
    "mapi-property": {
        "PropertyId": "16-bit MAPI property identifier (the high 16 bits of the property tag).",
        "PropertyType": "16-bit MAPI property type code (the low 16 bits of the property tag).",
        "Value": "Decoded property value; type depends on `PropertyType` (string, int, byte[], DateTime, etc.).",
        "Flags": "Property flags bitmask; controls multi-value, read-only, and other behavioral attributes.",
        "PropertyTag": "Combined 32-bit MAPI property tag: high 16 bits = PropertyId, low 16 bits = PropertyType.",
    },
    "mapi-property-collection": {
        "Set": "Adds `property` to the collection, replacing any existing entry with the same property tag.",
        "Add": "Constructs a new `MapiProperty` and adds it to the collection.",
        "Get": "Returns the `MapiProperty` matching `propertyId` and optional `propertyType`, or `null` if not found.",
        "Remove": "Removes the property identified by `propertyId` and optional `propertyType` from the collection.",
        "IterProperties": "Enumerates all `MapiProperty` entries in the collection.",
    },
    "mapi-recipient": {
        "DisplayName": "Recipient display name as stored in the MAPI recipient sub-storage.",
        "EmailAddress": "Recipient email address (SMTP address for SMTP-type entries).",
        "RecipientType": "Recipient type: 1 = To, 2 = Cc, 3 = Bcc.",
        "AddressType": "Address type string, typically `SMTP` or `EX` (Exchange).",
        "Properties": "Low-level MAPI property collection for this recipient's storage.",
    },
    "msg-document": {
        # Methods
        "FromFile": "Loads a `MsgDocument` from the `.msg` file at `path`; `strict` enables structural validation.",
        "FromStream": "Loads a `MsgDocument` from `stream`; `strict` enables structural validation.",
        "ToCfbDocument": "Converts this `MsgDocument` to a raw `CfbDocument` for low-level inspection or re-serialization.",
        # Properties
        "Root": "The root `MsgStorage` node of the message tree.",
        "MajorVersion": "CFB major version parsed from the file header.",
        "MinorVersion": "CFB minor version parsed from the file header.",
        "TransactionSignatureNumber": "CFB transaction signature number from the file header.",
        "Strict": "True if strict validation was requested when this document was loaded.",
    },
    "msg-reader": {
        # Methods
        "FromFile": "Opens the `.msg` file at `path` and returns a new `MsgReader`.",
        "FromStream": "Reads a `.msg` document from `stream` and returns a new `MsgReader`.",
        "Dispose": "Releases any file handle or stream held by this reader.",
        # Properties
        "ValidationIssues": "Read-only list of structural issues found during parsing; empty when the file is well-formed.",
    },
    "msg-storage": {
        # Methods
        "AddStream": "Adds `stream` as a child property stream of this storage.",
        "AddStorage": "Adds `storage` as a child sub-storage of this storage.",
        "FindStream": "Returns the `MsgStream` whose `Name` equals `name`, or `null` if not found.",
        "FindStorage": "Returns the `MsgStorage` whose `Name` equals `name`, or `null` if not found.",
        # Properties
        "Name": "CFB storage name for this node (e.g. `__substg1.0_0037001F` or `Root Entry`).",
        "Role": "Semantic role of this storage node as a `MsgStorageRole` value.",
        "Clsid": "16-byte CLSID of this storage entry; zeros for most MSG storages.",
        "StateBits": "User-defined state bits stored in the CFB directory entry for this storage.",
        "CreationTime": "CFB creation timestamp for this storage entry (64-bit FILETIME).",
        "ModifiedTime": "CFB last-modification timestamp for this storage entry (64-bit FILETIME).",
        "Streams": "Ordered list of `MsgStream` children of this storage.",
        "Storages": "Ordered list of `MsgStorage` child storages of this storage.",
    },
    "msg-storage-role": {
        "Generic": "Generic or unrecognized storage role.",
        "Message": "Root message storage containing all MAPI property streams.",
        "Recipient": "Recipient sub-storage (`__recip_version1.0_#XXXXXXXX`).",
        "Attachment": "Attachment sub-storage (`__attach_version1.0_#XXXXXXXX`).",
        "EmbeddedMessage": "Attachment sub-storage whose content is an embedded `.msg` message.",
        "NamedPropertyMapping": "Named-property-mapping storage (`__nameid_version1.0`).",
        "CustomAttachment": "Custom or non-standard attachment sub-storage.",
    },
    "msg-stream": {
        "Name": "CFB stream name encoding the MAPI property tag (e.g. `__substg1.0_0037001F`).",
        "Data": "Raw bytes of this property stream.",
        "Clsid": "16-byte CLSID of this stream entry (typically all zeros).",
        "StateBits": "User-defined state bits stored in the CFB directory entry for this stream.",
        "CreationTime": "CFB creation timestamp for this stream entry (64-bit FILETIME).",
        "ModifiedTime": "CFB last-modification timestamp for this stream entry (64-bit FILETIME).",
    },
    "msg-writer": {
        "ToBytes": "Serializes `document` to a valid `.msg` byte array.",
        "WriteFile": "Serializes `document` and writes it to the file at `path`.",
    },
}


def fill_member_descriptions(content, member_descs):
    """Fill in empty description cells in method/property/enum tables."""
    for member_name, desc in member_descs.items():
        # Match table rows where the name column contains member_name (as the first token)
        # and the description column is empty. The name may be in backticks or not.
        # Pattern: | `MemberName`... | ... | (empty) |
        # or: | MemberName(... | ... | (empty) |
        escaped = re.escape(member_name)
        # Match row starting with the member name (possibly in backticks, possibly with parens/args)
        pattern = rf'(\|\s*`?{escaped}[^|]*\|(?:[^|]*\|)*?)\s*(\|)'
        def replacer(m, _desc=desc):
            # Only replace if the last captured group (description cell) is empty/whitespace
            before = m.group(1)
            last_sep = m.group(2)
            # The description cell is the text immediately before the last |
            # Check if it ends with an empty cell: "| |" or "|  |"
            if re.search(r'\|\s*$', before):
                return before + _desc + ' ' + last_sep
            return m.group(0)

        # More targeted: split on lines and fix matching rows
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if line.strip().startswith('|') and member_name in line:
                # Check if description cell is empty (last non-empty segment)
                # Split carefully
                parts = line.split('|')
                # Find the description column (last non-empty header would tell us index)
                # Simpler: if the line ends with "| |" or "|  |" or "| \t|"
                if re.search(r'\|\s*\|?\s*$', line.rstrip()):
                    # Last cell is empty - fill it
                    # Strip trailing empty cell: "| |" at end
                    stripped = line.rstrip()
                    if stripped.endswith('|'):
                        # Check if second to last is empty
                        before_last = stripped[:-1].rstrip()
                        if before_last.endswith('|'):
                            # Empty last cell: add description
                            line = before_last + ' ' + desc + ' |'
            new_lines.append(line)
        content = '\n'.join(new_lines)
    return content


def update_page(path, old_overview, new_overview, member_descs=None):
    content = path.read_text(encoding='utf-8')
    if old_overview not in content:
        return False, f'overview not found'
    content = content.replace(old_overview, new_overview, 1)
    if member_descs:
        content = fill_member_descriptions(content, member_descs)
    path.write_text(content, encoding='utf-8')
    return True, 'ok'


changed = 0
errors = []
for stem, upd in OVERVIEWS.items():
    # Try .md directly
    path = REF / f'{stem}.md'
    if not path.exists():
        errors.append(f'NOT FOUND: {stem}.md')
        continue
    member_descs = MEMBER_DESCS.get(stem, {})
    ok, msg = update_page(path, upd['old'], upd['new'], member_descs)
    if ok:
        changed += 1
        print(f'  UPDATED: {stem}.md')
    else:
        errors.append(f'MISMATCH {stem}.md: {msg}')
        print(f'  MISMATCH: {stem}.md — {msg}')

if errors:
    print(f'\nErrors ({len(errors)}):')
    for e in errors:
        print(f'  {e}')
print(f'\nTotal updated: {changed}')
