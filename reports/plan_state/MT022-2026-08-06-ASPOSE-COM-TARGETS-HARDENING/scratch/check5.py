import sys, json
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline")
import requests
from commands.ops.fetch_aspose_com_targets import verify_url, configure

session = requests.Session()
session.headers.update({"User-Agent": "aspose-backlink-governance/1.0"})

candidates = [
    "https://docs.aspose.com/cells/typescript/",
    "https://products.aspose.com/cells/typescript/",
    "https://docs.aspose.com/email/python/",
    "https://products.aspose.com/email/python/",
    "https://docs.aspose.com/page/python/",
    "https://products.aspose.com/page/python/",
    "https://docs.aspose.com/tex/python/",
    "https://products.aspose.com/tex/python/",
    "https://docs.aspose.com/cad/net/",
    "https://products.aspose.com/cad/net/",
    "https://reference.aspose.com/cad/net/",
    "https://kb.aspose.com/cad/net/",
]

results = {}
for url in candidates:
    status, chain, resolved, via, retries = verify_url(url, session)
    results[url] = {"status": status, "resolved": resolved, "via": via, "retries": retries, "chain": chain}
    print(f"{url} -> {status} (resolved={resolved}, via={via}, retries={retries})", flush=True)

out_path = r"d:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING\scratch\check5_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("DONE, written to", out_path, flush=True)
