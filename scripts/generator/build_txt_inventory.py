#!/usr/bin/env python3
"""Build .txt inventory from local llms-output for TC-11 live verification.

Run after TC-08 pilot (all 5 domains generated).

Outputs:
  reports/llms-txt-verification/generated-txt-inventory.json
    Flat page inventory {domain: [page_url, ...]} — backward-compatible.
    Excludes root llms.txt, llms-full.txt, and nested llms.txt indexes.

  reports/llms-txt-verification/nested-indexes-inventory.json
    Nested index inventory {domain: [nested_llms_url, ...]}
    Contains only nested {family}/llms.txt and {family}/{platform}/llms.txt URLs.
    Root llms.txt and llms-full.txt are excluded (they are discovery roots, not indexes).
"""
import json
import os
import sys

DOMAINS = [
    'products.aspose.org', 'docs.aspose.org', 'blog.aspose.org',
    'kb.aspose.org', 'reference.aspose.org'
]

# Root-level files excluded from both inventories (they are discovery entry points)
ROOT_EXCLUDED = {'llms.txt', 'llms-full.txt'}


def _is_nested_llms(rel_path: str) -> bool:
    """Return True if rel_path is a nested llms.txt (not the domain root)."""
    # rel_path examples: 'pdf/net/llms.txt', 'pdf/llms.txt', 'llms.txt' (root)
    parts = rel_path.split('/')
    return parts[-1] == 'llms.txt' and len(parts) > 1


def main():
    base_dir = os.environ.get('LLMS_OUTPUT_DIR', 'llms-output')
    out_dir = 'reports/llms-txt-verification'
    os.makedirs(out_dir, exist_ok=True)

    inventory = {}       # page .txt files only
    nested_indexes = {}  # nested llms.txt files only

    for domain in DOMAINS:
        domain_base = os.path.join(base_dir, domain)
        if not os.path.isdir(domain_base):
            print(f"ERROR: {domain_base} not found — run generator first", file=sys.stderr)
            sys.exit(1)

        pages = []
        nested = []

        for root, _, files in os.walk(domain_base):
            for f in sorted(files):
                if not f.endswith('.txt'):
                    continue
                abs_path = os.path.join(root, f)
                rel = os.path.relpath(abs_path, domain_base).replace(os.sep, '/')

                # Skip root-level discovery files
                if rel in ROOT_EXCLUDED:
                    continue

                if _is_nested_llms(rel):
                    nested.append(f'https://{domain}/{rel}')
                else:
                    pages.append(f'https://{domain}/{rel}')

        if not pages:
            print(f"ERROR: {domain} has 0 .txt pages — generator may not have run", file=sys.stderr)
            sys.exit(1)

        inventory[domain] = sorted(pages)
        nested_indexes[domain] = sorted(nested)
        print(f"{domain}: {len(pages)} page .txt files, {len(nested)} nested index files")

    pages_path = os.path.join(out_dir, 'generated-txt-inventory.json')
    with open(pages_path, 'w') as f:
        json.dump(inventory, f, indent=2)
    print(f"Written: {pages_path}")

    nested_path = os.path.join(out_dir, 'nested-indexes-inventory.json')
    with open(nested_path, 'w') as f:
        json.dump(nested_indexes, f, indent=2)
    print(f"Written: {nested_path}")


if __name__ == '__main__':
    main()
