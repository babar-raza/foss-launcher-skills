---
page_role: feature_blog
description: Blog post introducing or announcing a product feature
min_words: 400
min_code_blocks: 1
required_sections:
  - heading: "Title (H1 via frontmatter title, not body H1)"
    required: true
    guidance: "Set in frontmatter title field, not as H1 in body"
  - heading: "Introduction paragraph"
    required: true
    guidance: "Lead paragraph: what is being announced and why it matters"
  - heading: "Key Features or main content section"
    required: true
    guidance: "The substantive content — features, code examples, use cases"
optional_sections:
  - heading: "Getting Started"
    guidance: "How to install and run the first example"
  - heading: "Code Example"
    guidance: "Runnable code showing the feature in action"
  - heading: "Conclusion"
    guidance: "Brief summary and call to action (link to docs)"
---

# Page Role: Feature Blog Post

## Purpose
Announces or introduces a product, feature, or release to a developer audience. More narrative than docs but still technically accurate.

## Required Elements

### Title
Set in YAML frontmatter as `title:`. Should be specific and action-oriented. Example: "Introducing Aspose.3D FOSS for Python — Open-Source 3D Processing".

### Introduction
First paragraph states what is being introduced and why it matters. Do not begin with "We are excited to announce". State the capability and its value directly.

### Key Features Section
Bullet list or subsections covering the main capabilities. Each capability bullet must be traceable to a claim in claims.json. Do not list capabilities not in the knowledge model.

### Code Example
At minimum one complete, runnable code example with correct imports and real API usage.

## Quality Standards
- Date in frontmatter must be accurate (not a placeholder)
- Author field required in frontmatter
- No marketing superlatives (robust, seamless, industry-leading)
- All format claims must match formats.json
- Code must use correct canonical import from install.md
- Evidence frontmatter: claims and apis populated
