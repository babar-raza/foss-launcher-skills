<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: A- -->
---
title: Installation
description: >-
  Learn the various methods to install {{PRODUCT_NAME}}, including
  {{PACKAGE_MANAGER}} (preferred), system installer, and archive options
weight: 11
type: docs
---

## Overview

{{PRODUCT_NAME}} is distributed as a standard package installable via {{PACKAGE_MANAGER}}. No build tools, SDKs, or admin rights are required. The package is self-contained and does not depend on any desktop application being installed on your system.

Supported platforms: Windows (x64), Linux (x64), macOS (Intel and Apple Silicon), Python 3.8+.

## System Requirements

Before installing, verify your environment meets these requirements:

- **Runtime version**: 3.8, 3.9, 3.10, 3.11, or 3.12
- **Package manager version**: 19.0 or later (verify with `--version`)
- **Operating system**: Windows 10/11, Ubuntu 18.04+, Debian 10+, macOS 11+
- **Disk space**: ~50 MB for the package and dependencies
- **Network access**: Required for the initial install; not required at runtime

```python
# Check your runtime version
import sys
print(f"Python {sys.version}")
# Expected: Python 3.8+ (CPython)
```

## Installation

Install the package using {{PACKAGE_MANAGER}}. Use the package name specific to the product you are using:

```python
# Install via package manager (run in terminal, not REPL)
# pip install {{PACKAGE_NAME}}
#
# Example:
import subprocess
result = subprocess.run(
    ["pip", "install", "{{PACKAGE_NAME}}"],
    capture_output=True, text=True, check=True
)
print(result.stdout)
print("Installation complete")
```

For virtual environments (recommended):

```python
# Create and activate a virtual environment first:
# python -m venv .venv
# .venv/Scripts/activate  (Windows)
# source .venv/bin/activate  (Linux/macOS)
# Then: pip install {{PACKAGE_NAME}}
```

## Verify Installation

After installation, verify it works by running a minimal import test:

```python
import library

# Create a minimal document to confirm the library is functional
doc = library.Document()
section = doc.sections[0]
section.content["A1"] = "Installation verified"
doc.save("verify_output.ext")

import os
assert os.path.exists("verify_output.ext"), "Output file not created"
print("{{PRODUCT_NAME}} installed and working correctly")
print(f"Output file size: {os.path.getsize('verify_output.ext')} bytes")
```

Run this script: `python verify_install.py`. If it prints "installed and working correctly", your setup is complete.

## Additional Resources

- [{{PRODUCT_NAME}} Product Page](/products/{{PRODUCT_FAMILY}}/)
- [{{PRODUCT_NAME}} API Reference](/reference/{{PRODUCT_FAMILY}}/)
- [{{PRODUCT_NAME}} Live Demos](/products/app/{{PRODUCT_FAMILY}}/)
- [{{PRODUCT_NAME}} Free Support Forum](/forum/)
