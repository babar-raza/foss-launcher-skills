"""extraction/outputs.py — Write scout extraction artifacts to disk.

Extracted from scout.py (SC-08). Standalone function usable without the
Scout class.

Public API::

    write_outputs(output, family, platform, manifest, classes, claims,
                  formats, limitations, snippets, class_graph, coverage,
                  scanned_files, packages, repo, language,
                  repo_sha, repo_url, scout_report=None)
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

import yaml

LOG = logging.getLogger("scout")

# Platform → file extension map (imported to avoid circular deps)
from extraction.tree_helpers import _FILE_EXTENSIONS  # noqa: E402


def _is_enum_class(c: dict) -> bool:
    """Return True if this class record represents an enum type.

    Handles two cases:
    - Native enum types (Java enum_declaration, C# enum_declaration, etc.)
    - Python IntEnum/Flag subclasses, which have kind="class_definition" but
      carry a populated enum_members list because _PY_ENUM_BASES detected them.
    """
    kind = c.get("kind", "")
    if kind in ("enum_declaration", "enum_definition"):
        return True
    # Python: IntEnum/StrEnum/Flag/IntFlag subclasses are class_definition nodes
    # that the api_surface extractor tagged with enum_members.
    if kind == "class_definition" and c.get("enum_members"):
        return True
    return False


def _install_command(platform: str, manifest: dict) -> str:
    name = manifest.get("name", "")
    version = manifest.get("version", "")
    if platform == "python":
        if name and version:
            return f"pip install {name}>={version}"
        return f"pip install {name}" if name else ""
    if platform in ("net", "dotnet"):
        if name and version:
            return f"dotnet add package {name} --version {version}"
        return f"dotnet add package {name}" if name else ""
    if platform == "java":
        gid = manifest.get("group_id", "")
        aid = manifest.get("artifact_id", "")
        if gid and aid:
            return (
                f"<!-- Maven -->\n<dependency>\n"
                f"  <groupId>{gid}</groupId>\n"
                f"  <artifactId>{aid}</artifactId>\n"
                f"  <version>{version}</version>\n"
                f"</dependency>"
            )
        return ""
    if platform in ("typescript", "javascript", "nodejs"):
        if name and version:
            return f"npm install {name}@{version}"
        return f"npm install {name}" if name else ""
    if platform == "cpp":
        return ""
    return ""


def _canonical_import(platform: str, manifest: dict,
                      packages: set[str] | None = None) -> str:
    name = manifest.get("name", "")
    if platform == "python":
        # Prefer an explicit canonical_package (set by package_manifest.py when
        # pyproject.toml contains [tool.setuptools.packages.find].include).
        # This correctly handles namespace packages like aspose/email_foss/ whose
        # import path (aspose.email_foss) differs from the PyPI name (aspose-email-foss).
        canonical_pkg = manifest.get("canonical_package", "")
        if canonical_pkg:
            return f"import {canonical_pkg}"
        pkg = name.replace("-", "_")
        return f"import {pkg}" if pkg else ""
    if platform in ("net", "dotnet"):
        return f"using {name};" if name else ""
    if platform == "java":
        # Prefer actual extracted package names (valid Java identifiers) over
        # the Maven artifact_id which may contain hyphens (illegal in Java packages).
        if packages:
            common_pkg = _common_java_package(packages)
            if common_pkg:
                return f"import {common_pkg}.*;"
        gid = manifest.get("group_id", "")
        if gid:
            return f"import {gid}.*;"
        return ""
    if platform in ("typescript", "javascript", "nodejs"):
        return f'import {{ ... }} from "{name}";' if name else ""
    if platform == "cpp" and packages:
        # Compute deepest common namespace prefix from extracted namespaces
        ns = _common_cpp_namespace(packages)
        if ns:
            return f"#include <{ns.replace('::', '/')}/...>"
    return ""


def _verify_command(platform: str, canonical_import: str) -> str:
    """Return a runnable shell command that verifies the installation.

    For Python the canonical_import is a statement (``import foo.bar``), not a
    shell command.  We wrap it in ``python -c "..."`` so the install.md
    ## Verify block is actually executable.
    """
    if platform == "python" and canonical_import.startswith("import "):
        module = canonical_import[len("import "):]
        return f'python -c "import {module}; print(\\"{module} OK\\")"'
    return canonical_import


def _common_cpp_namespace(packages: set[str]) -> str:
    """Find the deepest common namespace prefix from a set of C++ namespaces.

    Example: {"aspose::email::foss::cfb", "aspose::email::foss::msg"}
    -> "aspose::email::foss"
    """
    if not packages:
        return ""
    split_ns = [ns.split("::") for ns in packages if "::" in ns]
    if not split_ns:
        return ""
    prefix = split_ns[0]
    for parts in split_ns[1:]:
        new_len = min(len(prefix), len(parts))
        prefix = prefix[:new_len]
        for i in range(new_len):
            if prefix[i] != parts[i]:
                prefix = prefix[:i]
                break
    return "::".join(prefix) if prefix else ""


def _common_java_package(packages: set[str]) -> str:
    """Find the deepest common package prefix from a set of Java package names.

    Example: {"org.aspose.slides.foss", "org.aspose.slides.foss.drawing"}
    -> "org.aspose.slides.foss"
    """
    if not packages:
        return ""
    split_pkgs = [p.split(".") for p in packages if p]
    if not split_pkgs:
        return ""
    prefix = split_pkgs[0]
    for parts in split_pkgs[1:]:
        new_len = min(len(prefix), len(parts))
        prefix = prefix[:new_len]
        for i in range(new_len):
            if prefix[i] != parts[i]:
                prefix = prefix[:i]
                break
    return ".".join(prefix) if prefix else ""


def _runtime_requirement(platform: str, manifest: dict) -> str:
    if platform == "python":
        return manifest.get("requires_python", "")
    if platform in ("net", "dotnet"):
        return manifest.get("target_framework", "")
    if platform in ("typescript", "javascript", "nodejs"):
        return manifest.get("engines_node", "")
    if platform in ("java", "kotlin"):
        return manifest.get("runtime_min_version", "")
    if platform == "cpp":
        cmake_min = manifest.get("cmake_min_version", "")
        return f"CMake {cmake_min}+" if cmake_min else ""
    return ""


def write_outputs(
    output: Path,
    family: str,
    platform: str,
    manifest: dict,
    classes: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    formats: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
    snippets: list[dict[str, Any]],
    class_graph: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    scanned_files: list[str],
    packages: set[str],
    language: str,
    repo_sha: str,
    repo_url: str,
    package_root: str = "",
    scout_report: dict[str, Any] | None = None,
) -> None:
    """Write all scout extraction artifacts to *output* directory."""
    output.mkdir(parents=True, exist_ok=True)

    install_cmd = _install_command(platform, manifest)
    canonical_imp = _canonical_import(platform, manifest, packages)
    runtime_req = _runtime_requirement(platform, manifest)

    # model.yaml
    class_count = sum(1 for c in classes if c.get("kind") != "function")
    method_count = sum(len(c.get("methods", [])) for c in classes)
    prop_count = sum(len(c.get("properties", [])) for c in classes)
    enum_count = sum(1 for c in classes if _is_enum_class(c))

    model = {
        "family": family,
        "platform": platform,
        "product_name": manifest.get("name", f"Aspose.{family.upper()}-FOSS for {platform}"),
        "version": manifest.get("version", ""),
        "license": manifest.get("license", ""),
        "repo_sha": repo_sha,
        "repo_url": repo_url,
        "extracted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "scout",
        "package_root": package_root,
        "canonical_import": canonical_imp,
        "install_command": install_cmd,
        "runtime_requirement": runtime_req,
    }
    # C++-specific build metadata — only include when extracted
    if platform == "cpp":
        for _key in ("cmake_min_version", "library_target", "cpp_standard"):
            _val = manifest.get(_key, "")
            if _val:
                model[_key] = _val
    model["stats"] = {
        "class_count": class_count,
        "method_count": method_count,
        "property_count": prop_count,
        "enum_count": enum_count,
        "format_count": len(formats),
        "snippet_count": len(snippets),
        "limitation_count": len(limitations),
    }
    (output / "model.yaml").write_text(
        yaml.dump(model, default_flow_style=False, sort_keys=False,
                  allow_unicode=True),
        encoding="utf-8")
    LOG.info("Wrote model.yaml")

    # api_surface.json
    (output / "api_surface.json").write_text(
        json.dumps(classes, indent=2, ensure_ascii=False),
        encoding="utf-8")
    LOG.info("Wrote api_surface.json (%d entries)", len(classes))

    # claims.json
    (output / "claims.json").write_text(
        json.dumps(claims, indent=2, ensure_ascii=False),
        encoding="utf-8")
    LOG.info("Wrote claims.json (%d claims)", len(claims))

    # formats.json
    (output / "formats.json").write_text(
        json.dumps(formats, indent=2, ensure_ascii=False),
        encoding="utf-8")
    LOG.info("Wrote formats.json (%d formats)", len(formats))

    # limitations.md
    lim_lines = ["# Limitations (Not Implemented)\n"]
    if limitations:
        lim_lines.append("| File | Line | Class | Method | Code |")
        lim_lines.append("|------|------|-------|--------|------|")
        for lim in limitations:
            lim_lines.append(
                f"| {lim['file']} | {lim['line']} | {lim['class']} "
                f"| {lim['method']} | `{lim['text'][:80]}` |")
    else:
        lim_lines.append("No NotImplementedError patterns detected.")
    (output / "limitations.md").write_text(
        "\n".join(lim_lines) + "\n", encoding="utf-8")
    LOG.info("Wrote limitations.md (%d entries)", len(limitations))

    # install.md
    install_lines = [f"# Install {manifest.get('name', family)}\n"]
    if install_cmd:
        install_lines.append("```")
        install_lines.append(install_cmd)
        install_lines.append("```\n")
    if canonical_imp:
        verify_cmd = _verify_command(platform, canonical_imp)
        install_lines.append("## Verify\n")
        install_lines.append("```")
        install_lines.append(verify_cmd)
        install_lines.append("```\n")
    (output / "install.md").write_text(
        "\n".join(install_lines) + "\n", encoding="utf-8")
    LOG.info("Wrote install.md")

    # class_graph.json
    (output / "class_graph.json").write_text(
        json.dumps(class_graph, indent=2, ensure_ascii=False),
        encoding="utf-8")
    LOG.info("Wrote class_graph.json (%d edges)", len(class_graph))

    # coverage_matrix.json
    (output / "coverage_matrix.json").write_text(
        json.dumps(coverage, indent=2, ensure_ascii=False),
        encoding="utf-8")
    LOG.info("Wrote coverage_matrix.json (%d entries)", len(coverage))

    # absent_evidence.json
    absent_evidence = {
        "scan_complete": True,
        "scanned_file_count": len(scanned_files),
        "scanned_packages": sorted(packages),
        "found_classes": sorted(
            c["name"] for c in classes if c.get("kind") != "function"
        ),
        "found_enums": sorted(
            c["name"] for c in classes if _is_enum_class(c)
        ),
    }
    (output / "absent_evidence.json").write_text(
        json.dumps(absent_evidence, indent=2, ensure_ascii=False),
        encoding="utf-8")
    LOG.info("Wrote absent_evidence.json (%d classes, %d packages)",
             len(absent_evidence["found_classes"]),
             len(absent_evidence["scanned_packages"]))

    # snippets/
    snippets_dir = output / "snippets"
    snippets_dir.mkdir(exist_ok=True)
    ext = _FILE_EXTENSIONS.get(language, ".txt")
    index_entries: list[dict[str, Any]] = []
    for snip in snippets:
        snippet_id = snip.get("id", "")
        out_fname = snip.get("file", f"{snippet_id}{ext}")
        out_path = snippets_dir / out_fname
        out_path.write_text(snip.get("code", ""), encoding="utf-8")
        index_entries.append({
            "id": snippet_id,
            "file": out_fname,
            "source_file": snip.get("source_file", ""),
            "source_function": snip.get("source_function", ""),
            "source_line": snip.get("source_line", 0),
            "classes_used": snip.get("classes_used", []),
            "methods_used": snip.get("methods_used", []),
            "formats_referenced": snip.get("formats_referenced", []),
        })
    (snippets_dir / "snippets_index.json").write_text(
        json.dumps(index_entries, indent=2, ensure_ascii=False),
        encoding="utf-8")
    LOG.info("Wrote %d snippets + snippets_index.json", len(snippets))

    # scout_report.json (completeness tracking)
    if scout_report is not None:
        report_path = output / "scout_report.json"
        report_path.write_text(
            json.dumps(scout_report, indent=2, ensure_ascii=False),
            encoding="utf-8")
        LOG.info(
            "Wrote scout_report.json (attempted=%d, parsed=%d, skipped=%d, parse_errors=%d)",
            scout_report.get("files_attempted", 0),
            scout_report.get("files_parsed", 0),
            len(scout_report.get("files_skipped", [])),
            len(scout_report.get("parse_errors", [])),
        )
