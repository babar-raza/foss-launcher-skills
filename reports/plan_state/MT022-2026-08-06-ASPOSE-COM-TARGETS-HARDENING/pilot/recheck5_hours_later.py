import sys, json
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline")
import requests
from commands.ops.fetch_aspose_com_targets import verify_url

session = requests.Session()
session.headers.update({"User-Agent": "aspose-backlink-governance/1.0"})

candidates = [
    ("cells/typescript", "docs", "https://docs.aspose.com/cells/typescript/"),
    ("cells/typescript", "products", "https://products.aspose.com/cells/typescript/"),
    ("email/python", "docs", "https://docs.aspose.com/email/python/"),
    ("email/python", "products", "https://products.aspose.com/email/python/"),
    ("page/python", "docs", "https://docs.aspose.com/page/python/"),
    ("page/python", "products", "https://products.aspose.com/page/python/"),
    ("tex/python", "docs", "https://docs.aspose.com/tex/python/"),
    ("tex/python", "products", "https://products.aspose.com/tex/python/"),
    ("cad/net", "reference", "https://reference.aspose.com/cad/net/"),
    ("cad/net", "kb", "https://kb.aspose.com/cad/net/"),
    ("cad/net", "docs", "https://docs.aspose.com/cad/net/"),
    ("cad/net", "products", "https://products.aspose.com/cad/net/"),
]

results = {}
for key, sd, url in candidates:
    status, chain, resolved, via, retries = verify_url(url, session)
    results[f"{key}@{sd}"] = {"status": status, "via": via, "retries": retries}
    print(f"{key:20s} {sd:10s} {url:55s} -> {status} (via={via}, retries={retries})", flush=True)

out_path = r"d:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING\pilot\recheck5_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("DONE")
