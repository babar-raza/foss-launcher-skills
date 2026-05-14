#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
sites="${1:-products.aspose.org docs.aspose.org kb.aspose.org reference.aspose.org blog.aspose.org}"
pass=0
skip=0
fail=0

for site in $sites; do
  config=""
  for ext in toml yml yaml; do
    if [ -f "$repo_root/configs/$site.$ext" ]; then
      config="$repo_root/configs/$site.$ext"
      break
    fi
  done
  if [ -z "$config" ]; then
    echo "SKIP: $site"
    skip=$((skip + 1))
    continue
  fi
  if ! command -v hugo >/dev/null 2>&1; then
    echo "SKIP: $site (hugo unavailable)"
    skip=$((skip + 1))
    continue
  fi
  tmpdir="$(mktemp -d)"
  if hugo --config "$config" -d "$tmpdir" --quiet; then
    echo "PASS: $site"
    pass=$((pass + 1))
  else
    echo "FAIL: $site"
    fail=$((fail + 1))
  fi
  rm -rf "$tmpdir"
done

echo "Hugo Build Summary: $pass PASS, $fail FAIL, $skip SKIP"
[ "$fail" -eq 0 ]
