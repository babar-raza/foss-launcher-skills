import os, re
env_vars = {}
for root, dirs, files in os.walk("scripts"):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
    for f in files:
        if not f.endswith(".py"):
            continue
        path = os.path.join(root, f)
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
            for m in re.finditer(r'os\.(?:getenv|environ\.get)\(["\']([\w]+)', text):
                v = m.group(1)
                env_vars.setdefault(v, []).append(path)
            for m in re.finditer(r'os\.environ\[["\']([\w]+)', text):
                v = m.group(1)
                env_vars.setdefault(v, []).append(path)
        except Exception:
            pass
for v in sorted(env_vars):
    print(f"{v}  ({env_vars[v][0]})")
