---
page_role: howto_article
description: Step-by-step how-to guide for a specific task
min_words: 300
min_code_blocks: 1
required_sections:
  - heading: "Overview"
    required: true
    guidance: "1-2 sentences stating what this guide accomplishes"
  - heading: "Prerequisites"
    required: true
    guidance: "List required software versions, dependencies, and setup"
  - heading: "Step-by-step instructions or main content heading"
    required: true
    guidance: "The main procedural section — use numbered steps or clear h3 subsections"
  - heading: "Code example"
    required: true
    guidance: "At least one complete, runnable code example with correct import and correct API usage"
optional_sections:
  - heading: "Limitations"
    guidance: "Known constraints or unsupported scenarios"
  - heading: "See also"
    guidance: "Links to related pages"
---

# Page Role: How-To Article

## Purpose
Guides the reader through accomplishing a specific task using the product API. Must be actionable, complete, and directly runnable.

## Required Sections

### Overview
One or two sentences that tell the reader exactly what they will accomplish. Do not begin with "In this article" or "This page". State the outcome directly.

### Prerequisites
List exact requirements: package version, language runtime version, any other dependencies. Example: "Requires aspose-3d-foss >= 24.1 and Python 3.9+."

### Main Content
One or more sections that walk through the task. Headings should describe the action, not the concept (e.g., "Load a 3D Scene" not "Scene Loading"). Each section should have a code block.

### Code Example
Every code block must:
- Use the correct import statement from install.md
- Reference only class names and methods from api_surface.json
- Be syntactically correct for the platform
- Not reference NotImplementedError-raising methods

## Optional Sections

### Limitations
If the product has relevant limitations (from limitations.md), list them here. Use a table or bullet list.

### See Also
Up to 5 related links. Use relative internal links within the same subdomain.

## Quality Standards
- Minimum 300 words
- Minimum 1 code block
- All API names must be backtick-wrapped in prose
- No marketing language (robust, seamless, powerful, best)
- No unsupported format direction claims
- Evidence frontmatter required: claims + apis populated
