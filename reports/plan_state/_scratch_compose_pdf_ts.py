# -*- coding: utf-8 -*-
import json, re, sys

S = r"C:/Users/prora/AppData/Local/Temp/claude/d--onedrive-Documents-GitHub-aspose-org/9d8aa2aa-a458-4688-acc4-4048b8aa9955/scratchpad/pdfts"
D = "reports/repo-presenter-regen-full/pdf/typescript"

live = open(f"{S}/live_README.md", encoding="utf-8").read()
sections = json.load(open(f"{S}/sections.json", encoding="utf-8"))
modules = json.load(open("reports/plan_state/_scratch_pdf_ts_modules.json", encoding="utf-8"))

# --- pull the verbatim API overview body (whole section, minus its own H2 line) ---
h2 = [(m.start(), m.group(1).strip()) for m in re.finditer(r"^## (.+)$", live, re.M)]
h2.append((len(live), None))
api_overview_body = None
for i, (s, n) in enumerate(h2):
    if n == "API overview":
        api_overview_body = live[s:h2[i + 1][0]]
api_overview_body = re.sub(r"^## API overview\s*\n", "", api_overview_body, count=1).rstrip() + "\n"

development_body = None
for i, (s, n) in enumerate(h2):
    if n == "Development":
        development_body = live[s:h2[i + 1][0]]
development_body = re.sub(r"^## Development\s*\n", "", development_body, count=1).rstrip() + "\n"

limitations_body = sections["limitations_body"]
limitations_body = re.sub(r"^## Limitations\s*\n", "", limitations_body, count=1).rstrip() + "\n"

examples_by_old_heading = {e["old_heading"]: e["body"] for e in sections["examples"]}

# --- new headings for the 32 worked examples (task-oriented, title case) ---
NEW_HEADINGS = {
    "Encrypted PDFs": "Open Encrypted PDFs",
    "Encrypted output": "Write Encrypted Output",
    "Certificate-based (public-key) encryption": "Encrypt with Certificate-Based (Public-Key) Encryption",
    "Split and merge": "Split and Merge Documents",
    "Content streams": "Parse and Serialize Content Streams",
    "Text stamping": "Stamp Text on a Page",
    "Tables": "Build and Style Tables",
    "Table of contents": "Generate a Table of Contents",
    "Flow layout (`doc.NewFlow`)": "Build Multi-Column Flow Layouts",
    "Vector drawing": "Draw Vector Graphics",
    "Image insertion": "Insert Images",
    "Barcodes": "Generate Barcodes and QR Codes",
    "Layers (optional content)": "Manage Optional-Content Layers",
    "Text extraction": "Extract Text",
    "Vector path extraction": "Extract Vector Paths",
    "Text search": "Search Text",
    "Text replace": "Replace Text",
    "Redaction": "Redact Content",
    "Flatten annotations and forms": "Flatten Annotations and Forms",
    "Form fields (AcroForm)": "Create and Fill AcroForm Fields",
    "Form data (FDF / XFDF)": "Import and Export Form Data (FDF / XFDF)",
    "Outlines (bookmarks)": "Read and Write Outlines (Bookmarks)",
    "Page labels": "Read and Write Page Labels",
    "Named destinations": "Manage Named Destinations",
    "Document open behaviour and document-level JavaScript": "Set Document Open Behaviour and Document-Level JavaScript",
    "Annotations": "Create and Search Annotations",
    "Embedded files / attachments": "Embed Files and Attachments",
    "XMP metadata": "Read and Write XMP Metadata",
    "Images": "Extract and Replace Embedded Images",
    "File-based helpers": "Use File-Based Helper Methods",
    "Optimization": "Optimize Fonts, Images and Structure",
    "Grayscale conversion": "Convert Pages and Images to Grayscale",
}

ORDER = list(NEW_HEADINGS.keys())
assert set(ORDER) == set(examples_by_old_heading.keys()), (
    set(ORDER) ^ set(examples_by_old_heading.keys())
)

additional_examples_blocks = []
for old in ORDER:
    new_heading = NEW_HEADINGS[old]
    body = examples_by_old_heading[old]
    additional_examples_blocks.append(f"### {new_heading}\n\n{body}")
additional_examples_body = "\n".join(additional_examples_blocks)

# --- API Reference module-grouped class table (from real reference.aspose.org _index.md) ---
MODULE_ORDER = ["Core API", "Annotations", "Attachments", "Conversion", "Forms",
                "Redaction", "Security", "Structure", "Text"]
assert set(MODULE_ORDER) == set(modules.keys()), set(MODULE_ORDER) ^ set(modules.keys())
class_table_blocks = []
for mod in MODULE_ORDER:
    rows = modules[mod]
    lines = [f"### {mod}", "", "| Class | Description |", "|---|---|"]
    for name, desc in rows:
        lines.append(f"| `{name}` | {desc} |")
    class_table_blocks.append("\n".join(lines))
class_table_body = "\n\n".join(class_table_blocks)

print("additional examples chars:", len(additional_examples_body))
print("class table chars:", len(class_table_body))
print("api overview verbatim chars:", len(api_overview_body))
print("limitations verbatim chars:", len(limitations_body))
print("development verbatim chars:", len(development_body))

json.dump({
    "additional_examples_body": additional_examples_body,
    "class_table_body": class_table_body,
    "api_overview_body": api_overview_body,
    "limitations_body": limitations_body,
    "development_body": development_body,
    "new_headings": NEW_HEADINGS,
}, open(f"{S}/assembled_parts.json", "w", encoding="utf-8"), indent=1)
print("OK")
