---
page_role: faq
description: Frequently asked questions page
min_words: 200
min_code_blocks: 0
required_sections:
  - heading: "FAQ / Frequently Asked Questions (H1)"
    required: true
    guidance: "Top-level heading"
  - heading: "At least 5 Q&A pairs"
    required: true
    guidance: "Each question as H2 or H3, answer as paragraph(s)"
optional_sections:
  - heading: "Getting Started"
    guidance: "Category grouping installation and basic usage questions"
  - heading: "Format Support"
    guidance: "Category grouping questions about supported file formats"
  - heading: "Limitations"
    guidance: "Category grouping questions about limitations and unsupported features"
---

# Page Role: FAQ

## Purpose
Answers the most common questions about the product. Answers must be grounded in knowledge model claims — no speculation.

## Required Structure

### Q&A Format
Each question is a heading (H2 or H3). The answer immediately follows as one or more paragraphs.

Questions must be phrased as actual questions (end with "?"). Answers must be direct and factual.

**Good**: "### How do I install Aspose.3D FOSS for Python?"
**Bad**: "### Installation"

### Minimum 5 Q&A pairs
Recommended categories:
1. Installation / getting started question
2. At least one format support question (draw from formats.json)
3. At least one capability question (draw from claims.json kind=capability)
4. At least one limitation question (draw from limitations.md)
5. License / usage question

## Quality Standards
- Answers must be grounded in claims.json or formats.json
- No speculative answers ("probably", "might", "should")
- Format claims must match formats.json direction exactly
- All code snippets must use correct imports
- Evidence frontmatter: claims populated with referenced claim IDs
