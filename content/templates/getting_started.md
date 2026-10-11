---
page_role: docs
description: Getting started guide — product overview and first steps
min_words: 200
min_code_blocks: 1
required_sections:
  - heading: "Overview or Introduction"
    required: true
    guidance: "What the product is and what it does — drawn from claims.json"
  - heading: "Installation"
    required: true
    guidance: "Link to installation page OR inline install command"
  - heading: "Quick Start or First Example"
    required: true
    guidance: "The simplest complete code example — must use real API"
optional_sections:
  - heading: "Key Features"
    guidance: "Bullet list of main capabilities (from claims.json kind=capability)"
  - heading: "Next Steps"
    guidance: "Links to developer guide sections"
---

# Page Role: Getting Started / Overview

## Purpose
The first page a new user reads. Must be welcoming but factually grounded, and lead directly to a working example.

## Required Sections

### Overview
2-3 paragraphs: what the product is, what formats/operations it supports (from formats.json), what the primary use case is. Drawn entirely from merged claims and API surface.

### Installation
Either a direct install command (from install.md) OR a prominent link to the installation page. The reader must be unblocked within this page.

### Quick Start Example
The simplest meaningful example that demonstrates the product working. Must:
- Have correct import from install.md
- Use only real class names from api_surface.json
- Be completable in < 10 lines
- Produce observable output (print, file save, etc.)

## Quality Standards
- Do not mention limitations in the overview (link to limitations page instead)
- No version numbers in prose unless from model.yaml
- All class names and method names backtick-wrapped in prose
- Evidence frontmatter fully populated
