import json

before = json.load(open(r"reports/plan_state/MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING/scratch/aspose_com_targets_BEFORE.json", encoding="utf-8"))
after = json.load(open(r"data/aspose_com_targets.json", encoding="utf-8"))

print("=== provenance ===")
print("before generated_at:", before["provenance"]["generated_at"], " total_targets:", before["provenance"]["total_targets"])
print("after  generated_at:", after["provenance"]["generated_at"], " total_targets:", after["provenance"]["total_targets"])

print()
print("=== matrix diffs for affected families ===")
for fam in ["cells", "email", "page", "tex", "cad"]:
    b = before["family_platform_matrix"].get(fam, {})
    a = after["family_platform_matrix"].get(fam, {})
    print(f"-- {fam} --")
    print("  before:", {k: v for k, v in b.items() if "platforms" in k})
    print("  after :", {k: v for k, v in a.items() if "platforms" in k})

print()
print("=== all_urls counts ===")
print("before all_urls:", len(before.get("all_urls", {})))
print("after  all_urls:", len(after.get("all_urls", {})))
