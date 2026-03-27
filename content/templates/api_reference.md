---
page_role: api_reference
description: API reference page for a class or module
min_words: 150
min_code_blocks: 0
required_sections:
  - heading: "Class/Module name (H1)"
    required: true
    guidance: "The class or module being documented"
  - heading: "Overview or Description"
    required: true
    guidance: "What this class/module does — from docstring or claims.json"
optional_sections:
  - heading: "Constructor"
    guidance: "Constructor signature and parameters"
  - heading: "Properties"
    guidance: "Public properties with types"
  - heading: "Methods"
    guidance: "Public methods with signatures and brief descriptions"
  - heading: "Code Example"
    guidance: "Simple usage example"
  - heading: "See Also"
    guidance: "Links to related classes or guides"
---

# Page Role: API Reference

## Purpose
Documents a specific class, interface, enum, or module. Readers use this as a lookup reference, not a tutorial.

## Required Sections

### Class/Module Heading (H1)
The exact class name as it appears in api_surface.json. Do not add platform prefixes or language qualifiers.

### Overview
One paragraph describing what the class does, its primary purpose, and its key role in the API. Drawn from docstrings or api_surface.json description field. Do not fabricate capability claims.

## Optional but Highly Recommended

### Properties
Table format preferred: | Property | Type | Description |. Only include PUBLIC properties from api_surface.json.

### Methods
Table or definition-list format: Method signature + one-line description. Only include PUBLIC methods from api_surface.json. Mark deprecated or NotImplemented methods clearly.

### Code Example
Short, self-contained example showing the most common usage of this class.

## Quality Standards
- Class name in H1 must exactly match api_surface.json
- All method/property names must be in api_surface.json
- No fabricated parameters or return types
- NotImplementedError methods must be marked as such or omitted
- Evidence frontmatter: apis must include the documented class name
