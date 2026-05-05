# Translation Policy — Authoritative Reference

This document describes exactly what the translator reads, modifies, and preserves for each content type. The machine-readable source of truth is `policy/fields.yaml`; this document is its human-readable companion.

## Universal NEVER-TRANSLATE List

The following frontmatter keys are preserved verbatim regardless of content type. They are declared in `universal_preserve` in `fields.yaml` and merged into every content-type `preserve` list at load time.

```
evidence.*         — internal audit metadata (CRITICAL: never translated)
type               — Hugo page type
layout             — Hugo layout template
weight             — ordering integer
date               — publication date
lastmod            — last-modified date
draft              — boolean flag
slug               — URL slug override
url                — explicit URL override
aliases            — URL alias list
github_url         — source repo link
enable             — boolean toggle (used in products pages)
submenu            — navigation structure
more_formats       — format list widget data
back_to_top        — UI toggle
supportandlearning — support widget data
plugin_platform    — platform identifier (Windows, Linux, macOS …)
platformkey        — machine key for platform
productkey         — machine key for product
productplatform    — combined product+platform key
categories         — taxonomy list
```

## Per-Content-Type Policy

### `products.aspose.org`

Detected by: path contains `products.aspose.org`

**Translatable top-level frontmatter fields:**

| Field | Example value |
|---|---|
| `family_name` | `"Aspose.3D"` |
| `plugin_description` | `"A standalone .NET API for working with 3D files."` |
| `head_title` | `"3D File Processing .NET API"` |
| `head_description` | `"Process 3D files in .NET without any 3D software."` |
| `title` | `"Aspose.3D FOSS for .NET"` |
| `description` | `"Create, manipulate and convert 3D files."` |

**Translatable nested paths** (dot-notation; `[*]` means all array elements):

| Path | Description |
|---|---|
| `overview.title` | Section heading |
| `overview.content` | Overview prose |
| `content[*].title_left` | Feature card left heading |
| `content[*].title_right` | Feature card right heading |
| `content[*].content_left` | Feature card left body |
| `content[*].content_right` | Feature card right body |
| `single[*].title` | Single-column card heading |
| `single[*].content` | Single-column card body |
| `faq[*].question` | FAQ question text |
| `faq[*].answer` | FAQ answer text |
| `testimonialswrapper.title` | Testimonials section heading |
| `testimonialswrapper.subtitle` | Testimonials section subtitle |
| `testimonialswrapper.list[*].content` | Individual testimonial text |

**Body:** Translated. Protect shortcodes, code fences, inline code, URLs, block HTML.

---

### `docs.aspose.org`

Detected by: path contains `docs.aspose.org`

**Translatable frontmatter fields:**

| Field | Notes |
|---|---|
| `title` | Page title |
| `description` | Page meta description |

No nested paths are translated.

**Body:** Translated. Protect shortcodes, code fences, inline code, URLs, block HTML.

---

### `kb.aspose.org`

Detected by: path contains `kb.aspose.org`

**Translatable frontmatter fields:**

| Field | Notes |
|---|---|
| `title` | Article title |
| `description` | Article meta description |
| `keywords` | Keyword string or list |

`keywords` may be a string or a YAML list. When it is a list, each element is translated individually.

No nested paths are translated.

**Body:** Translated. Protect shortcodes, code fences, inline code, URLs, block HTML.

---

### `reference.aspose.org`

Detected by: path contains `reference.aspose.org`

**Translatable frontmatter fields:**

| Field | Notes |
|---|---|
| `linkTitle` | Sidebar / nav link label |
| `title` | Page title |
| `description` | Page meta description |

No nested paths are translated.

**Body:** Translated. Protect prose sections. Class names, method signatures, and parameter names that appear inside code fences or inline code are protected automatically by the pattern rules and will not be translated.

---

### `blog.aspose.org`

**SKIP. English only. No locale directories exist.**

The blog is hard-coded to `skip: true` in `fields.yaml`. `ContentTypePolicy.for_path()` returns a policy with `skip=True` for any path containing `blog.aspose.org`, and the CLI exits without writing any output for those paths.

---

## Body Protection Rules

The following regions are replaced with placeholder tokens (`⟦PH_0001⟧`, `⟦PH_0002⟧`, …) before the body is sent to the translation backend, then restored verbatim after translation. Any placeholder missing after translation raises `PlaceholderLeakError` immediately.

| Pattern name | Syntax | Behaviour |
|---|---|---|
| `shortcode_block` | `{{< ... >}}` and `{{% ... %}}` | Entire shortcode replaced; never translated |
| `code_fence` | ` ```lang ... ``` ` | Entire fenced block replaced; never translated |
| `code_fence_tilde` | `~~~lang ... ~~~` | Entire fenced block replaced; never translated |
| `inline_code` | `` `SomeClass.Method` `` | Inline span replaced; never translated |
| `markdown_link_url` | `[link text](url)` | URL part only replaced; link text is translated |
| `html_src` | `src="..."` and `href="..."` | Attribute value replaced; surrounding HTML translated |
| `block_html` | `<div>...</div>` etc. | Entire block replaced; never translated |
| `yaml_marker` | `---` at line start | Defensive guard; should not appear in body |

Patterns are applied in the order listed. Because shortcodes are matched first, a shortcode containing a code fence is protected as a single unit.

### URL handling

`[link text](url)` — the text portion flows through translation; the URL is held in a placeholder. This ensures translated pages have localised anchor text while keeping all href values intact.

### Evidence block

The `evidence` frontmatter key is a YAML mapping. It is never passed to any translation path. After writing the output file, validation code should call `HugoDocument.get_evidence()` on the output and confirm it is byte-for-byte identical to the source evidence block.
