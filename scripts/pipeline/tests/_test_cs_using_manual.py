"""Manual test for C# using statement extraction — no pytest required."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from token_ops import extract_tokens, _extract_from_code_line

FAILS = []


def check(name, condition, detail=""):
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}" + (f" — {detail}" if detail else ""))
        FAILS.append(name)


# --- Unit: _extract_from_code_line ---

var_types = {}
toks = _extract_from_code_line("from aspose.slides import Presentation", 1, var_types, "python")
check("Python from-import", any(t.kind == "import" and t.class_name == "aspose.slides" for t in toks))

toks = _extract_from_code_line("import aspose.slides", 2, {}, "python")
check("Python bare import", any(t.kind == "import" and t.class_name == "aspose.slides" for t in toks))

toks = _extract_from_code_line("using Aspose.Slides;", 3, {}, "net")
check("C# using Aspose.Slides", any(t.kind == "import" and t.class_name == "Aspose.Slides" for t in toks))

toks = _extract_from_code_line("using Aspose.ThreeD.Entities;", 4, {}, "net")
check("C# using Aspose.ThreeD.Entities", any(t.kind == "import" and t.class_name == "Aspose.ThreeD.Entities" for t in toks))

toks = _extract_from_code_line("using System.IO;", 5, {}, "net")
check("C# using System.IO (non-Aspose, still extracted)", any(t.kind == "import" and t.class_name == "System.IO" for t in toks))

toks = _extract_from_code_line("// using Aspose.Slides;", 6, {}, "net")
check("C# comment not extracted", toks == [], detail=str(toks))

# var_types not disrupted
vt = {}
_extract_from_code_line("scene = Scene()", 7, vt, "python")
check("var_types assignment tracking unchanged", vt.get("scene") == "Scene", detail=str(vt))

# --- Integration: extract_tokens from full markdown file ---

content = (
    "# Test\n\n"
    "```csharp\n"
    "using Aspose.Slides;\n"
    "using Aspose.Slides.Charts;\n"
    "```\n"
)
p = Path(tempfile.gettempdir()) / "test_cs_using.md"
p.write_text(content, encoding="utf-8")

tokens = extract_tokens(p, "net")
cs_imports = [t for t in tokens if t.kind == "import"]
check("Full file: 2 C# using tokens extracted", len(cs_imports) == 2, detail=f"got {[t.class_name for t in cs_imports]}")
check("Full file: Aspose.Slides found", any(t.class_name == "Aspose.Slides" for t in cs_imports))
check("Full file: Aspose.Slides.Charts found", any(t.class_name == "Aspose.Slides.Charts" for t in cs_imports))

# Python file not affected by C# path
py_content = (
    "# Python test\n\n"
    "```python\n"
    "from aspose.slides import Presentation\n"
    "prs = Presentation()\n"
    "```\n"
)
p2 = Path(tempfile.gettempdir()) / "test_py_import.md"
p2.write_text(py_content, encoding="utf-8")
py_tokens = extract_tokens(p2, "python")
py_imports = [t for t in py_tokens if t.kind == "import"]
check("Python file: import extracted (regression)", any(t.class_name == "aspose.slides" for t in py_imports))

# --- Summary ---
print()
if FAILS:
    print(f"FAILED: {len(FAILS)} test(s): {FAILS}")
    sys.exit(1)
else:
    print(f"All {9} checks passed.")
