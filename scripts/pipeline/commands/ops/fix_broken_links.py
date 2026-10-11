#!/usr/bin/env python3
"""Batch fix broken internal links across all content files.

Fixes three categories:
1. Cross-subdomain relative links (need absolute URLs)
2. Wrong slugs (slightly wrong page names)
3. Grouped reference slugs pointing to non-existent pages
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]  # up to aspose.org root

# Map of (file_relative_to_repo, old_link, new_link)
FIXES = [
    # === Blog 3d/java ===
    ("content/blog.aspose.org/3d/java/introducing-3d-foss-java/index.md",
     "(/docs/3d/java/)", "(https://docs.aspose.org/3d/java/)"),
    ("content/blog.aspose.org/3d/java/introducing-3d-foss-java/index.md",
     "(/kb/3d/java/)", "(https://kb.aspose.org/3d/java/)"),
    ("content/blog.aspose.org/3d/java/introducing-3d-foss-java/index.md",
     "(/reference/3d/java/)", "(https://reference.aspose.org/3d/java/)"),
    ("content/blog.aspose.org/3d/java/key-features-3d-java/index.md",
     "(/blog/3d/java/introducing-3d-foss-java/)", "(/3d/java/introducing-3d-foss-java/)"),
    ("content/blog.aspose.org/3d/java/working-with-3d-formats-in-java/index.md",
     "(/docs/3d/java/)", "(https://docs.aspose.org/3d/java/)"),

    # === Blog 3d/net ===
    ("content/blog.aspose.org/3d/net/3d-key-features-dotnet/index.md",
     "(/blog/3d/net/introducing-3d-foss-dotnet/)", "(/3d/net/introducing-3d-foss-dotnet/)"),
    ("content/blog.aspose.org/3d/net/3d-key-features-dotnet/index.md",
     "(/blog/3d/net/working-with-3d-formats-in-dotnet/)", "(/3d/net/working-with-3d-formats-in-dotnet/)"),
    ("content/blog.aspose.org/3d/net/introducing-3d-foss-dotnet/index.md",
     "(/docs/3d/net/)", "(https://docs.aspose.org/3d/net/)"),
    ("content/blog.aspose.org/3d/net/introducing-3d-foss-dotnet/index.md",
     "(/kb/3d/net/)", "(https://kb.aspose.org/3d/net/)"),
    ("content/blog.aspose.org/3d/net/introducing-3d-foss-dotnet/index.md",
     "(/reference/3d/net/)", "(https://reference.aspose.org/3d/net/)"),
    ("content/blog.aspose.org/3d/net/working-with-3d-formats-in-dotnet/index.md",
     "(/reference/3d/net/)", "(https://reference.aspose.org/3d/net/)"),
    ("content/blog.aspose.org/3d/net/working-with-3d-formats-in-dotnet/index.md",
     "(/kb/3d/net/)", "(https://kb.aspose.org/3d/net/)"),

    # === Blog 3d/typescript ===
    ("content/blog.aspose.org/3d/typescript/introducing-aspose-3d-foss-for-typescript/index.md",
     "(/kb/3d/typescript/how-to-load-3d-models-in-typescript/)",
     "(https://kb.aspose.org/3d/typescript/how-to-load-3d-models-in-typescript/)"),
    ("content/blog.aspose.org/3d/typescript/introducing-aspose-3d-foss-for-typescript/index.md",
     "(/kb/3d/typescript/how-to-export-gltf-in-typescript/)",
     "(https://kb.aspose.org/3d/typescript/how-to-export-gltf-in-typescript/)"),

    # === Docs 3d/typescript ===
    ("content/docs.aspose.org/en/3d/typescript/developer-guide/format-support.md",
     "(https://kb.aspose.org/3d/typescript/how-to-build-mesh-programmatically-in-typescript/)",
     "(https://kb.aspose.org/3d/typescript/how-to-build-mesh-in-typescript/)"),
    ("content/docs.aspose.org/en/3d/typescript/developer-guide/model-loading.md",
     "(https://reference.aspose.org/3d/typescript/api-overview/)",
     "(https://reference.aspose.org/3d/typescript/)"),
    ("content/docs.aspose.org/en/3d/typescript/developer-guide/rendering.md",
     "(https://reference.aspose.org/3d/typescript/api-overview/)",
     "(https://reference.aspose.org/3d/typescript/)"),
    ("content/docs.aspose.org/en/3d/typescript/developer-guide/scene-graph.md",
     "(https://kb.aspose.org/3d/typescript/how-to-build-mesh-programmatically-in-typescript/)",
     "(https://kb.aspose.org/3d/typescript/how-to-build-mesh-in-typescript/)"),

    # === Docs cells/python ===
    ("content/docs.aspose.org/en/cells/python/developer-guide/working-with-charts.md",
     "(https://blog.aspose.org/cells/python/python-excel-chart-tutorial/)",
     "(https://blog.aspose.org/cells/python/aspose-cells-foss-python-excel-chart-tutorial/)"),
    ("content/docs.aspose.org/en/cells/python/getting-started/_index.md",
     "(/cells/python/introducing-cells-foss-python/)",
     "(https://blog.aspose.org/cells/python/introducing-cells-foss-python/)"),
    ("content/docs.aspose.org/en/cells/python/getting-started/installation.md",
     "(/cells/python/introducing-cells-foss-python/)",
     "(https://blog.aspose.org/cells/python/introducing-cells-foss-python/)"),

    # === KB 3d/typescript ===
    ("content/kb.aspose.org/en/3d/typescript/how-to-export-gltf-in-typescript.md",
     "(/3d/typescript/gltfsaveoptions/)",
     "(https://reference.aspose.org/3d/typescript/GltfSaveOptions/)"),
    ("content/kb.aspose.org/en/3d/typescript/how-to-export-gltf-in-typescript.md",
     "(/3d/typescript/gltfformat/)",
     "(https://reference.aspose.org/3d/typescript/GltfFormat/)"),
    ("content/kb.aspose.org/en/3d/typescript/how-to-export-gltf-in-typescript.md",
     "(/3d/typescript/scene/)",
     "(https://reference.aspose.org/3d/typescript/scene/)"),
    ("content/kb.aspose.org/en/3d/typescript/how-to-load-3d-models-in-typescript.md",
     "(/3d/typescript/scene/)",
     "(https://reference.aspose.org/3d/typescript/scene/)"),
    ("content/kb.aspose.org/en/3d/typescript/how-to-load-3d-models-in-typescript.md",
     "(/3d/typescript/objloadoptions/)",
     "(https://reference.aspose.org/3d/typescript/ObjLoadOptions/)"),
    ("content/kb.aspose.org/en/3d/typescript/troubleshooting.md",
     "(https://reference.aspose.org/3d/typescript/api-overview/)",
     "(https://reference.aspose.org/3d/typescript/)"),

    # === KB cells/python ===
    ("content/kb.aspose.org/en/cells/python/_index.md",
     "(/cells/python/introducing-cells-foss-python/)",
     "(https://blog.aspose.org/cells/python/introducing-cells-foss-python/)"),

    # === Reference 3d/java ===
    ("content/reference.aspose.org/en/3d/java/_index.md",
     "(/3d/java/fvector/#fvector3)", "(FVector3/)"),
    ("content/reference.aspose.org/en/3d/java/_index.md",
     "(/3d/java/fvector/#fvector4)", "(FVector4/)"),
    ("content/reference.aspose.org/en/3d/java/_index.md",
     "(https://kb.aspose.org/3d/java/how-to-load-3d-models-in-java/)",
     "(https://kb.aspose.org/3d/java/how-to-load-3d-models-java/)"),
    ("content/reference.aspose.org/en/3d/java/_index.md",
     "(https://kb.aspose.org/3d/java/how-to-convert-3d-models-in-java/)",
     "(https://kb.aspose.org/3d/java/how-to-convert-3d-models-java/)"),

    # === Reference 3d/net ===
    ("content/reference.aspose.org/en/3d/net/_index.md",
     "(/kb/3d/net/how-to-load-3d-models-dotnet/)",
     "(https://kb.aspose.org/3d/net/how-to-load-3d-models-dotnet/)"),
    ("content/reference.aspose.org/en/3d/net/_index.md",
     "(/kb/3d/net/how-to-convert-3d-models-dotnet/)",
     "(https://kb.aspose.org/3d/net/how-to-convert-3d-models-dotnet/)"),

    # === Reference 3d/typescript _index.md — grouped slugs → individual pages ===
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/a3dobject-base/)", "(A3DObject/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/vertex-element-ts/)", "(VertexElement/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/vertex-element-ts/#vertexelementnormal)", "(VertexElementNormal/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/vertex-element-ts/#vertexelementuv)", "(VertexElementUV/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/vertex-element-ts/#vertexelementvertexcolor)", "(VertexElementVertexColor/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/format-options/)", "(ObjLoadOptions/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/property-assetinfo/#property)", "(Property/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/property-assetinfo/#propertycollection)", "(PropertyCollection/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/property-assetinfo/#assetinfo)", "(AssetInfo/)"),
    ("content/reference.aspose.org/en/3d/typescript/_index.md",
     "(/3d/typescript/property-assetinfo/)", "(Property/)"),
]


def apply_fixes():
    """Apply all link fixes."""
    files_modified = set()
    fixes_applied = 0
    fixes_failed = 0

    # Group fixes by file
    by_file = {}
    for rel_path, old, new in FIXES:
        by_file.setdefault(rel_path, []).append((old, new))

    for rel_path, replacements in by_file.items():
        fpath = REPO / rel_path
        if not fpath.exists():
            print(f"SKIP (not found): {rel_path}")
            continue

        content = fpath.read_text(encoding="utf-8")
        original = content

        for old, new in replacements:
            if old in content:
                content = content.replace(old, new, 1)
                fixes_applied += 1
            else:
                print(f"WARN (not found in file): {rel_path}: {old!r}")
                fixes_failed += 1

        if content != original:
            fpath.write_text(content, encoding="utf-8")
            files_modified.add(rel_path)

    # Special handling: reference/3d/typescript/_index.md has MANY /3d/typescript/format-options/ links
    # that need different replacements based on context
    ts_ref = REPO / "content/reference.aspose.org/en/3d/typescript/_index.md"
    if ts_ref.exists():
        content = ts_ref.read_text(encoding="utf-8")
        original = content

        # Replace remaining format-options links with contextual targets
        # These are links like [StlSaveOptions](/3d/typescript/format-options/)
        # Map by link text to correct target
        format_options_map = {
            "ObjLoadOptions": "ObjLoadOptions/",
            "ObjSaveOptions": "ObjSaveOptions/",
            "StlSaveOptions": "StlSaveOptions/",
            "StlLoadOptions": "StlLoadOptions/",
            "FbxSaveOptions": "FbxSaveOptions/",
            "FbxLoadOptions": "FbxLoadOptions/",
            "GltfSaveOptions": "GltfSaveOptions/",
            "GltfLoadOptions": "GltfLoadOptions/",
            "ColladaSaveOptions": "ColladaSaveOptions/",
            "ColladaLoadOptions": "ColladaLoadOptions/",
            "ThreeMfSaveOptions": "ThreeMfSaveOptions/",
            "ThreeMfLoadOptions": "ThreeMfLoadOptions/",
            "Format Load and Save Options": "ObjLoadOptions/",  # fallback to a representative page
        }

        # Fix pattern: [LinkText](/3d/typescript/format-options/)
        def fix_format_options(m):
            text = m.group(1)
            for key, target in format_options_map.items():
                if key in text:
                    return f"[{text}]({target})"
            return m.group(0)  # no change

        content = re.sub(
            r'\[([^\]]+)\]\(/3d/typescript/format-options/\)',
            fix_format_options,
            content
        )

        # Fix grouped reference links for a3dobject-base and vertex-element-ts (remaining instances)
        # [A3DObject, SceneObject, Entity reference](/3d/typescript/a3dobject-base/)
        content = re.sub(
            r'\[A3DObject, SceneObject, Entity reference\]\([^)]+\)',
            '[A3DObject](A3DObject/), [SceneObject](SceneObject/), [Entity](Entity/) reference',
            content
        )
        # [VertexElement, VertexElementNormal, VertexElementUV reference](/3d/typescript/vertex-element-ts/)
        content = re.sub(
            r'\[VertexElement, VertexElementNormal, VertexElementUV reference\]\([^)]+\)',
            '[VertexElement](VertexElement/), [VertexElementNormal](VertexElementNormal/), [VertexElementUV](VertexElementUV/) reference',
            content
        )
        # [Property, PropertyCollection, AssetInfo reference](/3d/typescript/property-assetinfo/)
        content = re.sub(
            r'\[Property, PropertyCollection, AssetInfo reference\]\([^)]+\)',
            '[Property](Property/), [PropertyCollection](PropertyCollection/), [AssetInfo](AssetInfo/) reference',
            content
        )

        if content != original:
            ts_ref.write_text(content, encoding="utf-8")
            files_modified.add("content/reference.aspose.org/en/3d/typescript/_index.md")
            # Count remaining format-options fixes
            remaining = content.count("/3d/typescript/format-options/")
            if remaining:
                print(f"WARN: {remaining} /3d/typescript/format-options/ links still remain")

        fixes_applied += original.count("/3d/typescript/format-options/") - content.count("/3d/typescript/format-options/")

    print(f"\nRESULT: {fixes_applied} fixes applied across {len(files_modified)} files, {fixes_failed} warnings")
    for f in sorted(files_modified):
        print(f"  MODIFIED: {f}")
    return 0 if fixes_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(apply_fixes())
