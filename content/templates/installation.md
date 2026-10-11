---
page_role: docs
description: Installation guide for a product platform
min_words: 150
min_code_blocks: 1
required_sections:
  - heading: "Requirements"
    required: true
    guidance: "Language runtime version, OS support, any system dependencies"
  - heading: "Installation"
    required: true
    guidance: "The install command(s) — must come from merged/install.md"
  - heading: "Verify Installation"
    required: false
    guidance: "Optional: a simple import or version check"
optional_sections:
  - heading: "License"
    guidance: "Link to license page"
  - heading: "Next Steps"
    guidance: "Link to getting started or developer guide"
---

# Page Role: Installation Guide

## Purpose
Tells the reader exactly how to install the product. Must be accurate and minimal.

## Required Sections

### Requirements
List minimum language runtime version (from merged/install.md), supported OS (if known), any system-level dependencies. Use a bullet list or table.

### Installation
The exact install command from merged/install.md. Do NOT fabricate or guess the package name. Examples:
- Python: `pip install aspose-3d-foss`
- Java: Maven `<dependency>` block from install.md
- .NET: `dotnet add package Aspose.3D.FOSS`

### Code Block
Wrap each install command in a code block with the correct language tag (bash, xml, shell).

## Quality Standards
- Package name must exactly match merged/install.md
- Version number must match model.yaml model_version
- Do not include installation steps for unrelated packages
- Evidence frontmatter: include model_sha and model_version
