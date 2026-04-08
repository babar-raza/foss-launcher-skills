"""Fix property Access column: Read -> Read/Write where api_surface says writable=True."""
import json
import re
from pathlib import Path

PROP_TABLE_ROW_RE = re.compile(
    r"^\|(\s*)`(?P<prop>[^`]+)`(\s*)\|([^|]+)\|\s*Read\s*\|",
    re.MULTILINE,
)


def fix_platform(family: str, platform: str) -> int:
    api_path = Path(f"knowledge/{family}/{platform}/merged/api_surface.json")
    if not api_path.exists():
        return 0
    api_data = json.loads(api_path.read_text(encoding="utf-8"))

    # Build class -> writable property set
    writable_map: dict[str, set] = {}
    for cls in api_data:
        name = cls.get("name", "")
        writable_map[name] = set()
        for prop in cls.get("properties", []):
            pname = prop.get("name", "")
            if pname and prop.get("writable", False):
                writable_map[name].add(pname)

    ref_dir = Path(f"content/reference.aspose.org/en/{family}/{platform}")
    if not ref_dir.exists():
        return 0

    fixes = 0
    for md in ref_dir.glob("*.md"):
        class_name = md.stem
        if class_name not in writable_map or not writable_map[class_name]:
            continue
        props = writable_map[class_name]
        content = md.read_text(encoding="utf-8")
        new_content = content
        for m in PROP_TABLE_ROW_RE.finditer(content):
            prop_name = m.group("prop")
            if prop_name in props:
                old = m.group(0)
                new = old.replace("| Read |", "| Read/Write |")
                new_content = new_content.replace(old, new, 1)
        if new_content != content:
            md.write_text(new_content, encoding="utf-8")
            fixes += 1
    return fixes


# Fix slides/net which has 52 FAILs
count = fix_platform("slides", "net")
print(f"slides/net: {count} pages fixed")
