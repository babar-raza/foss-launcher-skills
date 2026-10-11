# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, "scripts/pipeline/commands/foss")
import readme_refresh_checks as C

cand = open("reports/repo-presenter-regen-full/pdf/typescript/readme.md", encoding="utf-8").read()
content = json.load(open("reports/repo-presenter-regen-full/pdf/typescript/content-dispositions.json", encoding="utf-8"))

CANDIDATE_TARGETS = ["Key Capabilities", "API Reference", "Additional Examples", "Scope and Limitations",
                     "Development and Testing", "Documentation & Resources", "Installation", "Dependencies"]

still_bad = []
retargeted = 0
for entry in content:
    if entry.get("disposition") not in ("merged_verbatim", "merged_reframed"):
        continue
    original_target = entry.get("target_section")
    ok_target = None
    for t in [original_target] + [x for x in CANDIDATE_TARGETS if x != original_target]:
        entry["target_section"] = t
        findings = C.check_content_unit_merged_into_target_section(cand, [entry])
        if not findings:
            ok_target = t
            break
    if ok_target is None:
        entry["target_section"] = original_target
        still_bad.append(entry["unit_id"])
    else:
        if ok_target != original_target:
            retargeted += 1
        entry["target_section"] = ok_target

print("retargeted:", retargeted, "| still failing after trying all candidate targets:", len(still_bad))
print(still_bad[:60])

json.dump(content, open("reports/repo-presenter-regen-full/pdf/typescript/content-dispositions.json", "w", encoding="utf-8", newline="\n"),
          indent=2, ensure_ascii=False)
open("reports/repo-presenter-regen-full/pdf/typescript/content-dispositions.json", "a", encoding="utf-8", newline="\n").write("\n")
json.dump(still_bad, open("reports/plan_state/_content_still_bad.json", "w"), indent=1)
