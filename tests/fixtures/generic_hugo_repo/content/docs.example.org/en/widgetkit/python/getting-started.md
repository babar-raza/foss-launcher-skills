---
title: Getting Started with WidgetKit for Python
draft: false
---

# Getting Started with WidgetKit for Python

WidgetKit lets you build widgets programmatically.

## Installation

```bash
.venv/bin/pip install widgetkit
```

## Quick Example

```python
from widgetkit import Widget
w = Widget()
w.save("out.wgt")
```

## Supported Formats

| Format | Read | Write |
|--------|------|-------|
| WGT    | Yes  | Yes   |
| JSON   | Yes  | Yes   |
