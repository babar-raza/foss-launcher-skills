"""Tests for check_blog_post_standards.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow importing from scripts/ci/checks/ directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_blog_post_standards import (  # noqa: E402
    Finding,
    _check_post,
    _extract_family_platform,
    _is_blog_post,
    _parse_frontmatter,
    check_files,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post(tmp_path: Path, family: str, platform: str, slug: str, content: str) -> Path:
    """Create a fake blog post file at content/blog.aspose.org/{family}/{platform}/{slug}/index.md."""
    post_dir = tmp_path / "content" / "blog.aspose.org" / family / platform / slug
    post_dir.mkdir(parents=True)
    post_file = post_dir / "index.md"
    post_file.write_text(content, encoding="utf-8")
    return post_file


_GOOD_POST = """\
---
title: My Great Post
date: 2026-01-01
author: Aspose
categories:
- Aspose.PDF
tags: []
draft: false
---

Some content.

## Getting Started

- [Getting Started](https://docs.aspose.org/pdf/net/getting-started/)
- [Developer Guide](https://docs.aspose.org/pdf/net/developer-guide/)
- [KB Articles](https://kb.aspose.org/pdf/net/)
- [API Reference](https://reference.aspose.org/pdf/net/)

## Related Resources

- [Aspose.PDF for .NET — Enterprise Product](https://products.aspose.com/pdf/net/)
"""

_FAMILY_ROUTES = {"pdf": "Aspose.PDF", "cells": "Aspose.Cells", "3d": "Aspose.3D"}
_PLATFORMS = {"pdf/net", "pdf/go", "cells/net"}


# ---------------------------------------------------------------------------
# _is_blog_post
# ---------------------------------------------------------------------------

def test_is_blog_post_true():
    assert _is_blog_post("content/blog.aspose.org/pdf/net/my-post/index.md")


def test_is_blog_post_false_index():
    assert not _is_blog_post("content/blog.aspose.org/pdf/net/_index.md")


def test_is_blog_post_false_wrong_depth():
    assert not _is_blog_post("content/blog.aspose.org/pdf/my-post/index.md")


# ---------------------------------------------------------------------------
# _extract_family_platform
# ---------------------------------------------------------------------------

def test_extract_family_platform():
    family, platform = _extract_family_platform(
        "content/blog.aspose.org/pdf/net/my-post/index.md"
    )
    assert family == "pdf"
    assert platform == "net"


# ---------------------------------------------------------------------------
# C1 — tags must be empty
# ---------------------------------------------------------------------------

def test_c1_fail_nonempty_tags(tmp_path):
    content = """\
---
title: Test
author: Aspose
categories:
- Aspose.PDF
tags:
- pdf
draft: false
---
## Related Resources
- [Link](https://products.aspose.com/pdf/net/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert any(f.check == "C1" and f.level == "FAIL" for f in findings)


def test_c1_pass_empty_tags(tmp_path):
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C1" for f in findings)


def test_c1_skip_draft_post(tmp_path):
    content = """\
---
title: Draft Post
tags:
- pdf
draft: true
---
Content.
"""
    post = _make_post(tmp_path, "pdf", "net", "my-draft", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not findings  # draft posts are skipped entirely


# ---------------------------------------------------------------------------
# C2 — category format
# ---------------------------------------------------------------------------

def test_c2_fail_wrong_category(tmp_path):
    content = """\
---
title: Test
author: Aspose
categories:
- .NET
tags: []
draft: false
---
## Related Resources
- [Link](https://products.aspose.com/pdf/net/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert any(f.check == "C2" and f.level == "FAIL" for f in findings)


def test_c2_fail_absent_category(tmp_path):
    content = """\
---
title: Test
author: Aspose
tags: []
draft: false
---
## Related Resources
- [Link](https://products.aspose.com/pdf/net/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert any(f.check == "C2" and f.level == "FAIL" for f in findings)


def test_c2_pass_correct_category(tmp_path):
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C2" for f in findings)


def test_c2_pass_3d_family(tmp_path):
    """3d family uses 'Aspose.3D' (non-simple capitalization)."""
    content = """\
---
title: Test
author: Aspose
categories:
- Aspose.3D
tags: []
draft: false
---
## Related Resources
- [Link](https://products.aspose.com/3d/net/)
"""
    post = _make_post(tmp_path, "3d", "net", "my-post", content)
    findings = _check_post(post, "3d", "net", _FAMILY_ROUTES, {"3d/net"})
    assert not any(f.check == "C2" and f.level == "FAIL" for f in findings)


def test_c2_warn_unknown_family(tmp_path):
    content = """\
---
title: Test
author: Aspose
categories:
- Aspose.Zoom
tags: []
draft: false
---
## Related Resources
- [Link](https://products.aspose.com/zoom/net/)
"""
    post = _make_post(tmp_path, "zoom", "net", "my-post", content)
    findings = _check_post(post, "zoom", "net", _FAMILY_ROUTES, {"zoom/net"})
    assert any(f.check == "C2" and f.level == "WARN" for f in findings)


# ---------------------------------------------------------------------------
# C3 — Enterprise product link
# ---------------------------------------------------------------------------

def test_c3_fail_missing_enterprise_link(tmp_path):
    content = """\
---
title: Test
author: Aspose
categories:
- Aspose.PDF
tags: []
draft: false
---
No enterprise link here.
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert any(f.check == "C3" and f.level == "FAIL" for f in findings)


def test_c3_pass_enterprise_link_in_prose(tmp_path):
    """C3 passes when products.aspose.com link is in prose, not Related Resources."""
    content = """\
---
title: Test
author: Aspose
categories:
- Aspose.PDF
tags: []
draft: false
---
For enterprise features, see [Aspose.PDF](https://products.aspose.com/pdf/net/).

## Getting Started

- [Docs](https://docs.aspose.org/pdf/net/getting-started/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C3" for f in findings)


def test_c3_pass_has_related_resources(tmp_path):
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C3" for f in findings)


# ---------------------------------------------------------------------------
# C4 — No type: post (warning only)
# ---------------------------------------------------------------------------

def test_c4_warn_type_post(tmp_path):
    content = """\
---
title: Test
author: Aspose
categories:
- Aspose.PDF
tags: []
type: post
draft: false
---
## Related Resources
- [Link](https://products.aspose.com/pdf/net/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    c4 = [f for f in findings if f.check == "C4"]
    assert len(c4) == 1 and c4[0].level == "WARN"


def test_c4_no_warning_without_type_post(tmp_path):
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C4" for f in findings)


# ---------------------------------------------------------------------------
# C5 — Platform target registered
# ---------------------------------------------------------------------------

def test_c5_fail_platform_missing_from_json(tmp_path):
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    # Pass empty registered_platforms set to simulate missing entry
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, {"pdf/go"})
    assert any(f.check == "C5" and f.level == "FAIL" for f in findings)


def test_c5_pass_platform_registered(tmp_path):
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C5" for f in findings)


# ---------------------------------------------------------------------------
# Regression: cells/net posts should pass
# ---------------------------------------------------------------------------

def test_regression_cells_net_passes(tmp_path):
    content = """\
---
title: Cells .NET Post
author: Aspose
categories:
- Aspose.Cells
tags: []
draft: false
---
## Getting Started

- [Getting Started](https://docs.aspose.org/cells/net/getting-started/)
- [KB Articles](https://kb.aspose.org/cells/net/)

## Related Resources
- [Aspose.Cells for .NET — Enterprise Product](https://products.aspose.com/cells/net/)
"""
    post = _make_post(tmp_path, "cells", "net", "my-post", content)
    findings = _check_post(post, "cells", "net", _FAMILY_ROUTES, _PLATFORMS)
    fail_findings = [f for f in findings if f.level == "FAIL"]
    assert not fail_findings


# ---------------------------------------------------------------------------
# check_files integration (staged-file mode exit codes)
# ---------------------------------------------------------------------------

def test_check_files_pass(tmp_path):
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    result = check_files([str(post)], _FAMILY_ROUTES, _PLATFORMS)
    assert result == 0


def test_check_files_fail(tmp_path):
    content = """\
---
title: Bad Post
author: Aspose
categories:
- .NET
tags:
- pdf
draft: false
---
No related resources.
"""
    post = _make_post(tmp_path, "pdf", "net", "bad-post", content)
    result = check_files([str(post)], _FAMILY_ROUTES, _PLATFORMS)
    assert result == 1


def test_check_files_skips_non_blog_post(tmp_path):
    """Non-blog-post paths are silently skipped."""
    index = tmp_path / "content" / "blog.aspose.org" / "pdf" / "_index.md"
    index.parent.mkdir(parents=True)
    index.write_text("---\ntitle: Section\n---\n", encoding="utf-8")
    result = check_files([str(index)], _FAMILY_ROUTES, _PLATFORMS)
    assert result == 0


# ---------------------------------------------------------------------------
# C6 — Getting Started section
# ---------------------------------------------------------------------------

def test_c6_fail_no_getting_started(tmp_path):
    """Post with Related Resources but no Getting Started triggers C6 FAIL."""
    content = """\
---
title: Test Post
author: Aspose
categories:
- Aspose.PDF
tags: []
draft: false
---
Content here.

## Related Resources

- [Aspose.PDF for .NET — Enterprise Product](https://products.aspose.com/pdf/net/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert any(f.check == "C6" and f.level == "FAIL" for f in findings)


def test_c6_pass_with_getting_started_docs(tmp_path):
    """Post with Getting Started section pointing to docs.aspose.org passes C6."""
    content = """\
---
title: Test Post
author: Aspose
categories:
- Aspose.PDF
tags: []
draft: false
---
Content here.

## Getting Started

- [Getting Started](https://docs.aspose.org/pdf/net/getting-started/)

## Related Resources

- [Aspose.PDF for .NET — Enterprise Product](https://products.aspose.com/pdf/net/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C6" for f in findings)


def test_c6_pass_with_getting_started_kb(tmp_path):
    """Post with Getting Started section pointing to kb.aspose.org passes C6."""
    content = """\
---
title: Test Post
author: Aspose
categories:
- Aspose.Cells
tags: []
draft: false
---

## Getting Started

- [KB Articles](https://kb.aspose.org/cells/net/)

## Related Resources

- [Aspose.Cells for .NET — Enterprise Product](https://products.aspose.com/cells/net/)
"""
    post = _make_post(tmp_path, "cells", "net", "my-post", content)
    findings = _check_post(post, "cells", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.check == "C6" for f in findings)


def test_c6_pass_complete_post(tmp_path):
    """A fully correct post with both sections produces zero FAIL findings."""
    post = _make_post(tmp_path, "pdf", "net", "my-post", _GOOD_POST)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert not any(f.level == "FAIL" for f in findings)


def test_c6_fail_getting_started_no_aspose_link(tmp_path):
    """Getting Started section without an aspose.org link still triggers C6."""
    content = """\
---
title: Test Post
author: Aspose
categories:
- Aspose.PDF
tags: []
draft: false
---

## Getting Started

See the README for details.

## Related Resources

- [Aspose.PDF for .NET — Enterprise Product](https://products.aspose.com/pdf/net/)
"""
    post = _make_post(tmp_path, "pdf", "net", "my-post", content)
    findings = _check_post(post, "pdf", "net", _FAMILY_ROUTES, _PLATFORMS)
    assert any(f.check == "C6" and f.level == "FAIL" for f in findings)
