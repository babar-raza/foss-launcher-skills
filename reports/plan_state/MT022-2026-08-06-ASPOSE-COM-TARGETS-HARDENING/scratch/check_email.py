import sys, time, json
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline")
import requests

urls = ["https://docs.aspose.com/email/python/", "https://products.aspose.com/email/python/"]
results = {}
for url in urls:
    time.sleep(3)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    try:
        resp = session.get(url, allow_redirects=True, timeout=20)
        print(f"{url} -> {resp.status_code} (final url: {resp.url})", flush=True)
        results[url] = resp.status_code
    except Exception as e:
        print(f"{url} -> ERROR {e}", flush=True)
        results[url] = None

with open(r"d:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING\scratch\check_email_results.json", "w") as f:
    json.dump(results, f, indent=2)
