# Getting Started - Bootstrap the Repo Environment

Use this when someone just cloned the repo. The current bootstrap chain is:

```text
repo-scout -> knowledge-enrich -> truth-merge -> truth-index
```

Key current commands:

```bash
pip install -r scripts/requirements.txt
python scripts/pipeline/update_product_registry.py --token $GITHUB_TOKEN
cd scripts/pipeline
python scout.py {family} {platform} ../../runs/.clone_cache/aspose_{family}_{platform}/ ../../knowledge/{family}/{platform}/scout/
python enrich.py {family} {platform}
python promote.py {family} {platform}
python index.py {family} {platform}
python scripts/pipeline/audit.py {family} {platform}
```

Do not use `merge.py` or `truth-sync`; the FL-era flow has been removed.
