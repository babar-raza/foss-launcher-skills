<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: A- -->
---
description: Protect and encrypt documents with user-specified passwords and settings using {{PRODUCT_NAME}}.
title: "{{PRODUCT_NAME}} Document Protector"
type: docs
---


{{PRODUCT_NAME}} allows developers to programmatically protect documents and apply encryption with user-defined passwords and granular permission settings. Whether you want to prevent unauthorized edits, enforce document-level encryption, or restrict access to specific sections, this library delivers streamlined protection for your document files.

## Installation and Setup

To add {{PRODUCT_NAME}} to your project:

1. Install the package. See the [Installation](/docs/{{PRODUCT_FAMILY}}/getting-started/installation/) guide for details.
2. Configure metered licensing before using any API calls to avoid evaluation mode. Refer to the [Metered Licensing](/docs/{{PRODUCT_FAMILY}}/getting-started/metered-licensing/) documentation.

## Features and Functionalities

{{PRODUCT_NAME}} provides a comprehensive set of document processing features for the {{PLATFORM}} platform, including format support, security, and performance optimization.

### Supported File Formats

Applies protection to major document formats including legacy and modern open-standard formats. Protection settings remain intact across format conversions.

### Document-Level Encryption

Apply a password to encrypt the entire document. This uses standard encryption so the file cannot be opened without the correct password. Multiple encryption algorithms are supported for compatibility and security.

### Stream-Based Processing

* **Memory Buffer Support**: Protect files directly in memory without disk I/O.
* **Zero File System Access**: Complete protection workflow using streams.
* **Web Integration**: Process uploaded files and return protected versions instantly.
* **In-Memory Validation**: Verify password protection immediately after applying.

### Password Verification and Validation

* **Built-in Password Testing**: Verify that protection was applied correctly.
* **Exception-Based Validation**: Confirm files cannot be opened without correct password.
* **Programmatic Checks**: Use `FormatUtil.verify_password()` for password validation.
* **Security Testing**: Ensure protection mechanisms work as expected.

### Section Protection

Restrict editing at the section level with options such as:

* Locking cell contents
* Preventing row or column insertions/deletions
* Disabling sorting, filtering, or pivot operations

### Range-Level Protection

Define editable ranges while keeping formulas or sensitive data locked. Assign distinct passwords per range to grant limited access to specific user groups.

### Structure and Window Protection

Prevent document-wide changes like adding, renaming, or deleting sections. Lock view settings such as frozen panes or zoom levels to keep the user view consistent.

### Encryption Algorithms and Strength

Choose between AES-256 for high-security or legacy algorithms for compatibility. Algorithm selection is exposed via simple API settings.

### Protection Exceptions and Permissions

Fine-tune permissions by allowing certain actions (e.g., formatting or sorting) while keeping other features locked.

### Lock Management and Removal

Unlock sections, ranges, or entire documents programmatically with the correct password. APIs mirror the locking process, and protection status can be queried at runtime.

---

## Usage Examples

The following examples demonstrate common document processing patterns with {{PRODUCT_NAME}}, from basic operations through advanced batch processing workflows.

### Basic Document Protection with LowCode API

The simplest way to protect a document with a password:

```python
import library.lowcode as lc
import library

src = "template.xlsx"

load_opts = lc.LoadOptions()
load_opts.input_file = src

save_opts = lc.SaveOptions()
save_opts.save_format = library.SaveFormat.XLSX
save_opts.output_file = "protected.xlsx"

lc.Protector.process(load_opts, save_opts, "123", None)
print("Document protected successfully")
```

### Advanced: Stream-Based Protection with Validation

Process files entirely in memory and verify protection was applied correctly:

```python
import library.lowcode as lc
import library
import io

src = "template.xlsx"

# Configure load options
load_opts = lc.LoadOptions()
load_opts.input_file = src

# Configure save options
save_opts = lc.SaveOptions()
save_opts.save_format = library.SaveFormat.XLSX

# Output to memory buffer
buffer = io.BytesIO()
save_opts.output_stream = buffer

# Apply password protection (password: "123", unprotect password: None)
lc.Protector.process(load_opts, save_opts, "123", None)

# Reset buffer position for reading
buffer.seek(0)

# Verify password is correct
library.FormatUtil.verify_password(buffer, "123")

# Test that file is actually locked (should fail without password)
buffer.seek(0)
fail = False
try:
    library.Document(buffer)
    fail = True  # Should not reach here
except library.LibraryError as e:
    if e.code == library.ExceptionType.INCORRECT_PASSWORD:
        print("File is properly locked (cannot open without password)")
    else:
        print(f"Exception: {e.message}")

if fail:
    print("The resultant file should be locked with password but is not")

# Open with correct password (should succeed)
buffer.seek(0)
protected_doc = library.Document(buffer, load_options=library.LoadOptions(password="123"))
print("File opened successfully with correct password")
```

### Feature Breakdown: Password Protection Parameters

The `Protector.process()` method accepts four parameters:

```python
lc.Protector.process(
    load_options,      # Load configuration
    save_options,      # Save configuration and output destination
    "protect123",      # Password to protect the document
    None               # Unprotect password (optional, for removing existing protection)
)
```

**Parameter Details:**
- **Load Options**: Configures input file location and loading behavior
- **Save Options**: Configures output format, destination (file or stream)
- **Protection Password**: Password required to open the document
- **Unprotection Password**: Password to remove existing protection (use `None` if not needed)

### Feature Breakdown: Password Verification

Validate that protection was applied successfully:

```python
# Method 1: Use FormatUtil.verify_password()
buffer.seek(0)
is_valid = library.FormatUtil.verify_password(buffer, "123")
print(f"Password verification: {is_valid}")

# Method 2: Try opening without password (should fail)
buffer.seek(0)
try:
    library.Document(buffer)
    print("File is not properly protected")
except library.LibraryError as e:
    if e.code == library.ExceptionType.INCORRECT_PASSWORD:
        print("File is properly protected")

# Method 3: Open with correct password (should succeed)
buffer.seek(0)
doc = library.Document(buffer, load_options=library.LoadOptions(password="123"))
print("Correct password works")
```

### Feature Breakdown: Stream Position Management

When working with streams, proper positioning is critical:

```python
# After writing to stream
lc.Protector.process(load_opts, save_opts, "123", None)

# MUST reset position before reading
buffer.seek(0)  # Move to start of stream

# Now can read/verify
library.FormatUtil.verify_password(buffer, "123")

# Reset again for next operation
buffer.seek(0)
library.Document(buffer, load_options=library.LoadOptions(password="123"))
```

**Stream Position Best Practices:**
- Always `seek(0)` before reading from a stream you just wrote to
- Reset position between multiple read operations
- Use `seek(0)` consistently for clarity

### Feature Breakdown: Exception Handling for Protection

Handle different error scenarios when working with protected files:

```python
buffer.seek(0)

try:
    # Try to open without password
    doc = library.Document(buffer)
    print("Warning: File opened without password!")
except library.LibraryError as e:
    if e.code == library.ExceptionType.INCORRECT_PASSWORD:
        print("Password protection is active")
    elif e.code == library.ExceptionType.INVALID_FILE_FORMAT:
        print("File format is corrupted")
    elif e.code == library.ExceptionType.FILE_CORRUPTED:
        print("File is corrupted")
    else:
        print(f"Unexpected error: {e.message}")
```

### Traditional API: Granular Protection Control

For detailed protection scenarios, use the traditional Document API:

```python
import library

# Load a document
doc = library.Document("document.xlsx")

# Protect the entire document with a password
doc.protect(library.ProtectionType.ALL, "password123")

# Protect a specific section
section = doc.sections[0]
section.protect(library.ProtectionType.ALL, "sectionPass")

# Protect document structure
doc.settings.write_protection.password = "structurePass"

# Save the protected file
doc.save("locked_document.xlsx")
print("Protection applied successfully")
```

### Web API Integration Example

Protect uploaded documents in a web application:

```python
import library
import library.lowcode as lc
import io


class AdvancedProtectionService:
    def apply_multi_level_protection(self, input_path, output_path,
                                     file_password, section_password):
        """Apply both file-level and section-level protection."""
        # Protect the file with the Protector
        load_options = lc.LoadOptions()
        load_options.input_file = input_path

        # Use memory buffer for intermediate processing
        buffer = io.BytesIO()
        save_options = lc.SaveOptions()
        save_options.save_format = library.SaveFormat.XLSX
        save_options.output_stream = buffer

        # Apply file-level protection
        lc.Protector.process(load_options, save_options, file_password, None)

        # Now apply section-level protection
        buffer.seek(0)
        doc = library.Document(buffer, load_options=library.LoadOptions(password=file_password))

        # Protect all sections
        for section in doc.sections:
            section.protect(library.ProtectionType.ALL, section_password)

        # Save the document with both levels of protection
        doc.save(output_path)
        print("Multi-level protection applied")
```

### Batch Protection with Validation

Protect multiple files and verify each one:

```python
import os
import io
import library
import library.lowcode as lc

files = [f for f in os.listdir("input") if f.endswith(".xlsx")]
password = "SecurePass123!"

for filename in files:
    file_path = os.path.join("input", filename)
    try:
        load_opts = lc.LoadOptions()
        load_opts.input_file = file_path

        save_opts = lc.SaveOptions()
        save_opts.save_format = library.SaveFormat.XLSX

        buffer = io.BytesIO()
        save_opts.output_stream = buffer

        # Apply protection
        lc.Protector.process(load_opts, save_opts, password, None)

        # Verify protection
        buffer.seek(0)
        is_protected = False

        try:
            library.Document(buffer)  # Should fail
        except library.LibraryError as e:
            if e.code == library.ExceptionType.INCORRECT_PASSWORD:
                is_protected = True

        if is_protected:
            # Save to output directory
            output_file = os.path.join(
                "output",
                os.path.splitext(filename)[0] + "_protected.xlsx"
            )
            with open(output_file, "wb") as f:
                f.write(buffer.getvalue())
            print(f"Protected: {filename}")
        else:
            print(f"Failed to protect: {filename}")

    except Exception as ex:
        print(f"Error processing {filename}: {ex}")
```

### Removing Protection

Unlock protected documents programmatically:

```python
import library.lowcode as lc
import library

load_opts = lc.LoadOptions()
load_opts.input_file = "protected.xlsx"
load_opts.password = "123"  # Original password

save_opts = lc.SaveOptions()
save_opts.save_format = library.SaveFormat.XLSX
save_opts.output_file = "unprotected.xlsx"

# Pass empty string or None for both passwords to remove protection
lc.Protector.process(load_opts, save_opts, "", "")
print("Protection removed")
```

---

## Tips and Best Practices

Follow these guidelines to get the best results from {{PRODUCT_NAME}} in production deployments, covering security, performance, and resource management.

### Security Best Practices

* **Strong Passwords**: Use long, complex passwords with AES-256 for sensitive files.
* **Password Rotation**: Rotate passwords regularly in line with security policies.
* **Validation**: Always verify protection was applied using `FormatUtil.verify_password()` or exception testing.
* **Testing**: Test that files cannot be opened without the correct password.

### Stream Management

* **Position Reset**: Always call `buffer.seek(0)` before reading from a stream you wrote to.
* **Cleanup**: Close streams promptly to free memory.
* **Reuse**: Reset and reuse streams for batch processing to reduce memory pressure.

### Performance Optimization

* **LowCode API**: Use `Protector.process()` for optimized performance.
* **Batch Processing**: Process multiple files in parallel for high-throughput scenarios.
* **Memory Streams**: Use streams for web applications to avoid disk I/O overhead.

### Protection Strategies

* **Layered Protection**: Combine section and range protections with document-level passwords.
* **Metadata Storage**: Persist protection settings in configuration for automation tasks.
* **Format Preservation**: Reapply protection after format conversions to ensure encryption integrity.
* **Permission Checks**: Use `is_protected` checks before performing operations to avoid exceptions.

### Production Deployment

* **Initialize Once**: Initialize licensing at startup to avoid evaluation warnings.
* **Error Handling**: Implement comprehensive exception handling for `LibraryError` types.
* **Logging**: Log protection operations and validation results for audit trails.
* **Cleanup**: Delete temporary files after processing in web applications.

---

## Common Issues and Resolutions

| Issue | Resolution |
|-------|------------|
| **File not properly protected** | Verify password is not empty string; check `FormatUtil.verify_password()` result |
| **Cannot open protected file** | Ensure you're using `LoadOptions` with correct `password` property |
| **Stream read fails** | Call `buffer.seek(0)` to reset stream position before reading |
| **Exception: IncorrectPassword** | This is expected when testing protection; catch and handle `ExceptionType.INCORRECT_PASSWORD` |
| **Memory buffer is empty** | Ensure `Protector.process()` completed successfully before reading stream |
| **File opens without password** | Check that protection was applied; may need to use traditional API for specific protection types |
| **Cannot verify password** | Stream position may be at end; reset with `seek(0)` |
| **Document.protect() not working** | LowCode API uses different protection mechanism; use appropriate API for your needs |

---

## Frequently Asked Questions

**What is {{PRODUCT_NAME}}?**
A specialized tool for applying password protection and encryption to documents programmatically in {{PLATFORM}} applications.

**How does it differ from the full {{PRODUCT_FAMILY}} library?**
{{PRODUCT_FAMILY}} is a comprehensive library. The Protector provides streamlined APIs focused specifically on protection and encryption workflows.

**What types of protection are supported?**
Document-level encryption (requires password to open), section protection, range protection, and structure protection.

**Can I protect files in memory without saving to disk?**
Yes! Use `io.BytesIO()` with `SaveOptions.output_stream` for complete in-memory processing.

**How do I verify protection was applied correctly?**
Use `FormatUtil.verify_password()` or try opening the file without a password (should throw `INCORRECT_PASSWORD` exception).

**What do the four parameters of Protector.process() mean?**
1. Load options (input configuration)
2. Save options (output configuration)
3. Protection password (to lock the file)
4. Unprotection password (to remove existing locks, use `None` if not needed)

**Why do I need to call seek() on the stream?**
After writing to a stream, the position is at the end. You must reset to the beginning with `seek(0)` before reading.

**Can I use different passwords for different sections?**
Yes, but you'll need to use the traditional `Document` API's per-section protection methods rather than the LowCode API.

**How do I remove password protection?**
Pass empty strings or None for both password parameters, or use the traditional API's `unprotect()` method.

**What encryption algorithms are supported?**
Standard encryption including AES-128, AES-256, and legacy algorithms for compatibility.

---

## API Reference Summary

The {{PRODUCT_NAME}} API is organized around a small set of core classes that handle document loading, processing, and output configuration.

### Key Classes

- **`Protector`**: Class providing simplified protection methods
- **`LoadOptions`**: Configuration for loading document files
- **`SaveOptions`**: Configuration for output (file or stream)
- **`FormatUtil`**: Utility class for password verification
- **`LoadOptions`**: Options for opening protected documents

### Essential Properties

- **`input_file`**: Source document file path
- **`output_file`**: Target file path (file-based output)
- **`output_stream`**: Target stream (stream-based output)
- **`save_format`**: Output file format
- **`password`**: Password for opening protected documents (in `LoadOptions`)

### Key Methods

- **`Protector.process(load_opts, save_opts, password, unprotect_password)`**: Apply password protection
- **`FormatUtil.verify_password(stream, password)`**: Verify a password is correct
- **`buffer.seek(0)`**: Reset stream position for reading
- **`Document.protect(type, password)`**: Traditional API protection method
- **`Document.unprotect(password)`**: Remove protection from document

### Exception Types

- **`ExceptionType.INCORRECT_PASSWORD`**: Raised when opening protected file without correct password
- **`ExceptionType.INVALID_FILE_FORMAT`**: File format is not recognized
- **`ExceptionType.FILE_CORRUPTED`**: File structure is damaged
