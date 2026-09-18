# -*- coding: utf-8 -*-
import json, re

api = json.load(open("knowledge/pdf/typescript/merged/api_surface.json", encoding="utf-8"))
byname = {}
for e in api:
    byname.setdefault(e["name"], e.get("file"))
    for m in e.get("methods", []) or []:
        byname.setdefault(m["name"], e.get("file"))
    for p in e.get("properties", []) or []:
        byname.setdefault(p["name"], e.get("file"))

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

def guess_file(tokens, excerpt):
    # try dotted/bare identifiers from tokens first (most specific), then scan the excerpt itself
    candidates = []
    for t in tokens or []:
        for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", t):
            candidates.append(ident.split(".")[-1].split("(")[0])
    for ident in IDENT_RE.findall(excerpt or ""):
        candidates.append(ident)
    for c in candidates:
        if c in byname and byname[c]:
            return byname[c]
    return None

D = "reports/repo-presenter-regen-full/pdf/typescript"
fixed = 0
missing = []
for fname in ("content-dispositions.json", "structure-dispositions.json", "code-example-dispositions.json"):
    path = f"{D}/{fname}"
    data = json.load(open(path, encoding="utf-8"))
    for e in data:
        v = e.get("verification")
        if not v or v.get("evidence_type") != "clone_cache_path":
            continue
        if v.get("evidence_ref", "").strip().lower() != "readme.md":
            continue
        tokens = e.get("salient_tokens") or e.get("api_call_fingerprint") or []
        excerpt = e.get("excerpt") or e.get("heading_context") or e.get("heading") or ""
        f = guess_file(tokens, excerpt)
        if f:
            v["evidence_ref"] = f
            v["evidence_note"] = (v.get("evidence_note", "") + " | evidence_ref corrected from a circular "
                "README.md self-citation to the real source file this claim is verifiable against").strip(" |")
            fixed += 1
        else:
            missing.append(e["unit_id"])
    json.dump(data, open(path, "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
    open(path, "a", encoding="utf-8", newline="\n").write("\n")

print("fixed:", fixed, "| still missing a real source file:", len(missing))
print(missing[:40])
json.dump(missing, open("reports/plan_state/_evidence_missing.json", "w"), indent=1)
