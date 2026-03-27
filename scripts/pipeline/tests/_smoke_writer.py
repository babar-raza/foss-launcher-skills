"""Smoke tests for evidence/writer.py without pytest dependency."""
import re, sys, textwrap, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evidence.writer import _write_evidence_to_frontmatter

_EVIDENCE_BLOCK_RE = re.compile(
    r"^evidence:[ \t]*(?:\n[ \t]+[^\n]*)*", re.MULTILINE
)
_SAMPLE = {
    "model_sha": "abc123",
    "model_version": "1.0",
    "claims": ["CLM-001"],
    "apis": ["Foo.bar"],
}


def apply(content, ev=None):
    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(content)
        tmp = Path(f.name)
    _write_evidence_to_frontmatter(tmp, dict(ev or _SAMPLE))
    r = tmp.read_text()
    tmp.unlink()
    return r


def strip_ev(text):
    m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not m:
        return text
    fm = _EVIDENCE_BLOCK_RE.sub("", m.group(2)).rstrip("\n") + "\n"
    return m.group(1) + fm + m.group(3) + text[m.end():]


passed = failed = 0


def ok(name):
    global passed
    passed += 1
    print(f"  PASS  {name}")


def fail(name, msg):
    global failed
    failed += 1
    print(f"  FAIL  {name}: {msg}")


# -------------------------------------------------------------------
# 1. Literal block scalar preserved
# -------------------------------------------------------------------
t1 = textwrap.dedent("""\
    ---
    title: Test
    content: |
      Install with pip:

      ```python
      from lib import Foo
      ```
    ---

    Body.
""")
r1 = apply(t1)
if "content: |" in r1 and "```python" in r1 and 'content: "' not in r1:
    ok("preserves_literal_block_scalar")
else:
    fail("preserves_literal_block_scalar", repr(r1[:400]))

# -------------------------------------------------------------------
# 2. All non-evidence bytes identical
# -------------------------------------------------------------------
t2 = textwrap.dedent("""\
    ---
    layout: plugin
    title: "My Title"
    overview:
      content: |
        Para one.

        Para two.
    ---

    Body.
""")
r2 = apply(t2)
if strip_ev(t2) == strip_ev(r2):
    ok("preserves_all_non_evidence_bytes")
else:
    fail(
        "preserves_all_non_evidence_bytes",
        f"\nORIG: {repr(strip_ev(t2))}\nRESULT: {repr(strip_ev(r2))}",
    )

# -------------------------------------------------------------------
# 3. Evidence inserted when absent
# -------------------------------------------------------------------
t3 = "---\ntitle: Page\n---\n\nBody.\n"
r3 = apply(t3)
if "evidence:" in r3 and "model_sha: abc123" in r3:
    ok("evidence_inserted_when_absent")
else:
    fail("evidence_inserted_when_absent", repr(r3))

# -------------------------------------------------------------------
# 4. Claims merged with existing
# -------------------------------------------------------------------
t4 = textwrap.dedent("""\
    ---
    title: Page
    evidence:
      model_sha: old
      model_version: '0.9'
      claims:
      - CLM-OLD
      apis: []
    ---

    Body.
""")
r4 = apply(t4, {"model_sha": "new", "model_version": "2.0", "claims": ["CLM-NEW"], "apis": []})
if "CLM-OLD" in r4 and "CLM-NEW" in r4 and "model_sha: new" in r4:
    ok("claims_merged_with_existing")
else:
    fail("claims_merged_with_existing", repr(r4))

# -------------------------------------------------------------------
# 5. Idempotent (no duplicate evidence block)
# -------------------------------------------------------------------
t5 = "---\ntitle: Page\n---\n\nBody.\n"
r5a = apply(t5)
r5b = apply(r5a)
if r5b.count("evidence:") == 1:
    ok("idempotent_second_run")
else:
    fail("idempotent_second_run", f"evidence count: {r5b.count('evidence:')}\n{r5b}")

# -------------------------------------------------------------------
# 6. No frontmatter creates one
# -------------------------------------------------------------------
t6 = "Just body.\n"
r6 = apply(t6)
if r6.startswith("---\n") and "evidence:" in r6 and "Just body." in r6:
    ok("no_frontmatter_creates_one")
else:
    fail("no_frontmatter_creates_one", repr(r6))

# -------------------------------------------------------------------
# 7. Real-world product page pattern (single.block with | scalars)
# -------------------------------------------------------------------
t7 = textwrap.dedent("""\
    ---
    layout: plugin
    title: Aspose.Cells FOSS for Python
    single:
      enable: true
      block:
      - title: Create a Workbook
        content: |
          Install with pip, then create a Workbook.

          ```bash
          pip install aspose-cells-foss
          ```

          ```python
          from aspose.cells_foss import Workbook

          wb = Workbook()
          ws = wb.worksheets[0]
          ws.cells["A1"].value = "Hello"
          wb.save("out.xlsx")
          ```
      - title: Build a Chart
        content: |
          Open the workbook and add a chart.

          ```python
          from aspose.cells_foss import Workbook

          wb = Workbook("out.xlsx")
          ws = wb.worksheets[0]

          chart = ws.charts.add_bar(5, 0, 15, 6)
          chart.title = "Sales"

          wb.save("out_chart.xlsx")
          ```
    ---

    Body.
""")
r7 = apply(t7)
if (
    r7.count("content: |") == 2
    and "```python" in r7
    and "wb.save" in r7
    and 'content: "' not in r7
    and strip_ev(t7) == strip_ev(r7)
):
    ok("real_world_product_page_pattern")
else:
    fail("real_world_product_page_pattern", f"count={r7.count('content: |')}\n{r7[:600]}")

# -------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"{passed} passed, {failed} failed")
if failed:
    sys.exit(1)
