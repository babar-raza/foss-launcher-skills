# Adapted from aspose.org
"""Batch-generate all missing site plan pages."""
import yaml, os, json
from datetime import datetime

today = datetime.now().strftime("%Y-%m-%d")

PLATFORM_CONFIG = {
    "net": {"lang": "csharp", "suffix": "dotnet", "install_cmd": "dotnet add package", "human": ".NET"},
    "java": {"lang": "java", "suffix": "java", "install_cmd": "Maven <dependency>", "human": "Java"},
    "python": {"lang": "python", "suffix": "python", "install_cmd": "pip install", "human": "Python"},
    "cpp": {"lang": "cpp", "suffix": "cpp", "install_cmd": "CMake FetchContent", "human": "C++"},
    "typescript": {"lang": "typescript", "suffix": "typescript", "install_cmd": "npm install", "human": "TypeScript"},
}

FAMILY_FOSS = {
    "3d": "Aspose.3D FOSS", "cells": "Aspose.Cells FOSS", "email": "Aspose.Email FOSS",
    "font": "Aspose.Font FOSS", "note": "Aspose.Note FOSS", "slides": "Aspose.Slides FOSS",
    "words": "Aspose.Words FOSS",
}

PACKAGE_NAMES = {
    ("3d","net"): "Aspose.3D.Foss", ("3d","java"): "com.aspose:aspose-3d-foss",
    ("3d","python"): "aspose-3d", ("3d","typescript"): "@aspose/3d",
    ("cells","net"): "Aspose.Cells.Foss", ("cells","java"): "com.aspose:aspose-cells-foss",
    ("cells","python"): "aspose-cells", ("cells","typescript"): "@aspose/cells",
    ("email","net"): "Aspose.Email.Foss", ("email","cpp"): "aspose-email-cpp",
    ("email","python"): "aspose-email",
    ("font","python"): "aspose-font", ("note","python"): "aspose-note",
    ("slides","net"): "Aspose.Slides.Foss", ("slides","java"): "com.aspose:aspose-slides-foss",
    ("slides","python"): "aspose-slides", ("slides","cpp"): "aspose-slides-cpp",
    ("words","python"): "aspose-words",
}


def load_api_surface(family, platform):
    path = "knowledge/" + family + "/" + platform + "/merged/api_surface.json"
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return {c.get("name", ""): c for c in data}
    return data


def load_model_sha(family, platform):
    path = "knowledge/" + family + "/" + platform + "/merged/model.yaml"
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        m = yaml.safe_load(f)
    return m.get("stats", {}).get("repo_sha", "") or m.get("repo_sha", "") or ""


def slug_to_title(slug):
    s = slug.replace("working-with-", "").replace("how-to-", "").replace("-", " ")
    return s.title()


def find_classes(api_classes, cluster):
    cluster_lower = cluster.lower().replace("-", "").replace("_", "")
    matches = []
    for name in api_classes:
        if cluster_lower in name.lower() or name.lower() in cluster_lower:
            matches.append(name)
    return matches[:5]


def make_page_title(page_name):
    titles = {
        "format-support": "Format Support",
        "animation": "Working with Animation",
        "materials-shading": "Materials and Shading",
        "scene-entities": "Scene Entities",
        "compound-file-support": "Compound File Support",
        "message-parsing": "Message Parsing",
        "onestore-format": "OneStore Format",
        "ms-one": "Working with MS OneNote Files",
        "features": "Features and Capabilities",
        "license": "License Information",
        "validation": "Working with Data Validation",
    }
    for key, val in titles.items():
        if key in page_name:
            return val
    t = slug_to_title(page_name)
    if not t.startswith("Working"):
        t = "Working with " + t
    return t


def gen_docs(pi, api, sha):
    fam, plat = pi["family"], pi["platform"]
    slug, weight, cluster = pi["slug"], pi["weight"], pi.get("cluster", "")
    pc = PLATFORM_CONFIG[plat]
    foss = FAMILY_FOSS[fam]
    pkg = PACKAGE_NAMES.get((fam, plat), foss.lower())
    page_name = slug.split("/")[-1]
    title = make_page_title(page_name)
    classes = find_classes(api, cluster or page_name)

    if page_name == "license":
        return _license_page(fam, plat, pc, foss, pkg, weight, sha)
    if page_name == "features":
        return _features_page(fam, plat, pc, foss, pkg, weight, sha, api)

    desc_cls = ", ".join(classes[:3]) if classes else "the core API"
    lines = [
        "---\n",
        "page_role: howto_article",
        'title: "' + title + " -- " + foss + " for " + pc["human"] + '"',
        'linktitle: "' + title + '"',
        "description: >-",
        "  Learn how to work with " + title.lower() + " using " + foss + " for " + pc["human"] + ".",
        "  Covers " + desc_cls + ".",
        "weight: " + str(weight),
        "type: docs",
        "provenance:",
        "  content_origin: skill-generated",
        "  last_mechanism: skill",
        "  auto_updatable: true",
        "evidence:",
        '  model_sha: "' + sha + '"',
        '  model_version: ""',
        "  claims: []",
        "  apis: []",
        "\n---\n",
        foss + " for " + pc["human"] + " provides classes for working with " + title.lower() + ".",
        "",
        "---",
        "",
        "## Overview",
        "",
    ]
    if classes:
        lines.append("The key classes involved are:\n")
        for cn in classes:
            c = api.get(cn, {})
            d = c.get("docstring", "") if isinstance(c, dict) else ""
            lines.append("- **`" + cn + "`**" + (" -- " + d[:80] if d else ""))
    lines += [
        "", "---", "",
        "## Getting Started", "",
        "Install " + foss + " for " + pc["human"] + ":", "",
        "```bash\n" + pc["install_cmd"] + " " + pkg + "\n```", "",
    ]
    if classes:
        entry = classes[0]
        lines += [
            "### Basic Usage", "",
            "```" + pc["lang"],
            "// Basic usage of " + entry,
            "// See reference documentation for full API details",
            "```", "",
        ]
    lines += [
        "---", "",
        "## Tips and Best Practices", "",
        "- Always dispose of document objects after use",
        "- Handle file I/O exceptions when reading or writing files",
        "- Check the [API reference](https://reference.aspose.org/" + fam + "/" + plat + "/) for the latest signatures",
        "", "---", "",
        "## API Reference Summary", "",
    ]
    if classes:
        lines.append("| Class | Description |")
        lines.append("|-------|-------------|")
        for cn in classes:
            c = api.get(cn, {})
            d = c.get("docstring", "") if isinstance(c, dict) else ""
            lines.append("| `" + cn + "` | " + (d[:60] if d else "See reference docs") + " |")
    lines.append("\nFor full details, see the [API Reference](https://reference.aspose.org/" + fam + "/" + plat + "/).\n")
    return "\n".join(lines)


def _license_page(fam, plat, pc, foss, pkg, weight, sha):
    return (
        "---\n\npage_role: howto_article\ntitle: License Information\ndescription: >-\n"
        "  Understand the licensing model for " + foss + " for " + pc["human"] + ". This FOSS library\n"
        "  is available under the MIT License with no license key required.\n"
        "weight: " + str(weight) + "\ntype: docs\nprovenance:\n  content_origin: skill-generated\n"
        "  last_mechanism: skill\n  auto_updatable: true\nevidence:\n"
        '  model_sha: "' + sha + '"\n  model_version: ""\n  claims: []\n  apis: []\n\n---\n\n'
        + foss + " for " + pc["human"] + " is an open-source library released under the **MIT License**. No license key or activation is needed.\n\n---\n\n"
        "## MIT License\n\nThe MIT License permits:\n\n"
        "- Free use in commercial and non-commercial projects\n- Modification and redistribution\n- Private use without disclosure\n\n"
        "The only requirement is to include the original copyright notice and license text.\n\n---\n\n"
        "## No License Key Required\n\nUnlike proprietary Aspose products, " + foss + " for " + pc["human"] + " does **not** require a license file. Simply install:\n\n"
        "```bash\n" + pc["install_cmd"] + " " + pkg + "\n```\n\n---\n\n"
        "## Differences from Proprietary Products\n\n"
        "| Aspect | " + foss + " | Proprietary |\n|--------|--------|-------------|\n"
        "| License | MIT | Commercial |\n| License key | No | Yes |\n| Source code | Open | Closed |\n| Support | Community | Paid |\n\n---\n\n"
        "### FAQ\n\n#### Is there a watermark or evaluation limitation?\n\nNo. " + foss + " for " + pc["human"] + " produces clean output.\n\n"
        "#### Can I use it in a commercial product?\n\nYes. The MIT License explicitly allows commercial use.\n"
    )


def _features_page(fam, plat, pc, foss, pkg, weight, sha, api):
    cc = len(api)
    cls_list = list(api.keys())[:15]
    lines = ["---\n", "page_role: howto_article", "title: Features and Capabilities", "description: >-",
        "  Complete feature list of " + foss + " for " + pc["human"] + ".",
        "weight: " + str(weight), "type: docs", "provenance:", "  content_origin: skill-generated",
        "  last_mechanism: skill", "  auto_updatable: true", "evidence:",
        '  model_sha: "' + sha + '"', '  model_version: ""', "  claims: []", "  apis: []",
        "\n---\n",
        foss + " for " + pc["human"] + " provides a comprehensive API with " + str(cc) + " public classes.",
        "", "---", "", "## Key Capabilities", ""]
    for cn in cls_list:
        c = api.get(cn, {})
        d = c.get("docstring", "") if isinstance(c, dict) else ""
        lines.append("- **" + cn + "**" + (" -- " + d[:80] if d else ""))
    if cc > 15:
        lines.append("\n...and " + str(cc - 15) + " more classes.")
    lines += ["", "---", "",
        "For the full API reference, see the [reference documentation](https://reference.aspose.org/" + fam + "/" + plat + "/).", ""]
    return "\n".join(lines)


def gen_kb(pi, api, sha):
    slug = pi["slug"]
    fam, plat = pi["family"], pi["platform"]
    pc = PLATFORM_CONFIG[plat]
    foss = FAMILY_FOSS[fam]
    pkg = PACKAGE_NAMES.get((fam, plat), foss.lower())
    if slug == "use-cases":
        return _use_cases(fam, plat, pc, foss, pkg, sha)
    if slug == "troubleshooting":
        return _troubleshooting(fam, plat, pc, foss, pkg, sha)
    return _howto(pi, api, sha)


def _howto(pi, api, sha):
    fam, plat = pi["family"], pi["platform"]
    slug, weight, cluster = pi["slug"], pi["weight"], pi.get("cluster", "")
    pc = PLATFORM_CONFIG[plat]
    foss = FAMILY_FOSS[fam]
    pkg = PACKAGE_NAMES.get((fam, plat), foss.lower())
    title = slug_to_title(slug)
    classes = find_classes(api, cluster or slug)
    entry = classes[0] if classes else ""
    step2 = ("2. Use the `" + entry + "` class for the core operation.") if entry else "2. Import the library and use the relevant classes."
    ref_target = entry or "usage"
    return (
        '---\ntitle: "' + title + '"\ndescription: >-\n  ' + title + " using " + foss + " for " + pc["human"] + '.\n'
        'date: "' + today + '"\nlastmod: "' + today + '"\nweight: ' + str(weight) + '\ndraft: false\ntype: topic\n'
        "keywords:\n- " + plat + " " + fam + " " + slug.replace("-", " ") + "\n- aspose " + fam + " foss " + pc["suffix"] + "\n"
        "provenance:\n  content_origin: skill-generated\n  last_mechanism: skill\n  auto_updatable: true\n"
        'evidence:\n  model_sha: "' + sha + '"\n  model_version: ""\n  claims: []\n  apis: []\n\n---\n\n'
        "This guide shows how to " + title.lower() + " using " + foss + " for " + pc["human"] + ".\n\n---\n\n"
        "## Prerequisites\n\n| Requirement | Detail |\n|-------------|--------|\n"
        "| Runtime | " + pc["human"] + " |\n| Package | `" + pkg + "` |\n| Install | `" + pc["install_cmd"] + " " + pkg + "` |\n\n---\n\n"
        "## Steps\n\n1. Install the package:\n\n```bash\n" + pc["install_cmd"] + " " + pkg + "\n```\n\n"
        + step2 + "\n\n```" + pc["lang"] + "\n// See API reference for " + ref_target + " details\n```\n\n---\n\n"
        "## Tips and Best Practices\n\n"
        "- Check the [API reference](https://reference.aspose.org/" + fam + "/" + plat + "/) for the latest class signatures\n"
        "- Handle file I/O exceptions when reading or writing files\n- Dispose of resources properly after use\n\n---\n\n"
        "## Related Resources\n\n- [Developer Guide](https://docs.aspose.org/" + fam + "/" + plat + "/developer-guide/)\n"
        "- [API Reference](https://reference.aspose.org/" + fam + "/" + plat + "/)\n"
    )


def _use_cases(fam, plat, pc, foss, pkg, sha):
    return (
        '---\ntitle: "Use Cases -- ' + foss + " for " + pc["human"] + '"\ndescription: >-\n'
        "  Common use cases for " + foss + " for " + pc["human"] + " in production applications.\n"
        'date: "' + today + '"\nlastmod: "' + today + '"\nweight: 10\ndraft: false\ntype: topic\n'
        "keywords:\n- " + fam + " " + plat + " use cases\n- aspose " + fam + " foss " + pc["suffix"] + " examples\n"
        "provenance:\n  content_origin: skill-generated\n  last_mechanism: skill\n  auto_updatable: true\n"
        'evidence:\n  model_sha: "' + sha + '"\n  model_version: ""\n  claims: []\n  apis: []\n\n---\n\n'
        + foss + " for " + pc["human"] + " is suitable for a range of document-processing scenarios.\n\n---\n\n"
        "## Document Generation\n\nGenerate files programmatically from data sources, templates, or application logic.\n\n"
        "```bash\n" + pc["install_cmd"] + " " + pkg + "\n```\n\n---\n\n"
        "## File Format Conversion\n\nConvert between supported file formats without requiring external software.\n\n---\n\n"
        "## Data Extraction\n\nRead and extract data, metadata, and structural information from existing files.\n\n---\n\n"
        "## Automated Processing\n\nIntegrate into CI/CD pipelines, batch-processing workflows, or microservices.\n\n---\n\n"
        "## Related Resources\n\n- [Developer Guide](https://docs.aspose.org/" + fam + "/" + plat + "/developer-guide/)\n"
        "- [API Reference](https://reference.aspose.org/" + fam + "/" + plat + "/)\n"
        "- [FAQ](https://kb.aspose.org/" + fam + "/" + plat + "/faq/)\n"
    )


def _troubleshooting(fam, plat, pc, foss, pkg, sha):
    return (
        '---\ntitle: "Troubleshooting -- ' + foss + " for " + pc["human"] + '"\ndescription: >-\n'
        "  Common issues and solutions when using " + foss + " for " + pc["human"] + ".\n"
        'date: "' + today + '"\nlastmod: "' + today + '"\nweight: 2\ndraft: false\ntype: topic\n'
        "keywords:\n- " + fam + " " + plat + " troubleshooting\n- aspose " + fam + " foss errors " + pc["suffix"] + "\n"
        "provenance:\n  content_origin: skill-generated\n  last_mechanism: skill\n  auto_updatable: true\n"
        'evidence:\n  model_sha: "' + sha + '"\n  model_version: ""\n  claims: []\n  apis: []\n\n---\n\n'
        "This page covers common issues and their solutions when using " + foss + " for " + pc["human"] + ".\n\n---\n\n"
        "## Package Installation Fails\n\n**Symptom**: Package installation command fails with dependency errors.\n\n"
        "**Fix**: Ensure your runtime version meets the minimum requirement. Run:\n\n"
        "```bash\n" + pc["install_cmd"] + " " + pkg + "\n```\n\n---\n\n"
        "## File Not Found or Access Denied\n\n**Symptom**: An exception is thrown when opening or saving a file.\n\n"
        "**Fix**: Verify the file path exists and your application has read/write permissions.\n\n---\n\n"
        "## Unsupported File Format\n\n**Symptom**: An exception is thrown when loading a file in an unsupported format.\n\n"
        "**Fix**: Check the [supported formats documentation](https://docs.aspose.org/" + fam + "/" + plat + "/developer-guide/).\n\n---\n\n"
        "## Related Resources\n\n- [Developer Guide](https://docs.aspose.org/" + fam + "/" + plat + "/developer-guide/)\n"
        "- [API Reference](https://reference.aspose.org/" + fam + "/" + plat + "/)\n"
        "- [FAQ](https://kb.aspose.org/" + fam + "/" + plat + "/faq/)\n"
    )


def gen_blog(pi, api, sha):
    fam, plat = pi["family"], pi["platform"]
    slug, cluster = pi["slug"], pi.get("cluster", "")
    pc = PLATFORM_CONFIG[plat]
    foss = FAMILY_FOSS[fam]
    pkg = PACKAGE_NAMES.get((fam, plat), foss.lower())
    title = slug_to_title(slug)
    classes = find_classes(api, cluster or slug)
    cls_lines = ""
    if classes:
        cls_lines = "The key classes for this feature area include:\n\n"
        for cn in classes:
            c = api.get(cn, {})
            d = c.get("docstring", "") if isinstance(c, dict) else ""
            cls_lines += "- **`" + cn + "`**" + (" -- " + d[:80] if d else "") + "\n"
    return (
        '---\ntitle: "' + title + " -- " + foss + " for " + pc["human"] + '"\ndescription: >-\n'
        "  Deep dive into " + title.lower() + " with " + foss + " for " + pc["human"] + ".\n"
        'date: "' + today + '"\nlastmod: "' + today + '"\ndraft: false\nauthor: Aspose Team\nsummary: >-\n'
        "  Learn about " + title.lower() + " capabilities in " + foss + " for " + pc["human"] + ".\n"
        "provenance:\n  content_origin: skill-generated\n  last_mechanism: skill\n  auto_updatable: true\n"
        'evidence:\n  model_sha: "' + sha + '"\n  model_version: ""\n  claims: []\n  apis: []\n\n---\n\n'
        + foss + " for " + pc["human"] + " provides powerful capabilities for working with " + title.lower() + ".\n\n"
        "## Overview\n\n" + cls_lines + "\n## Getting Started\n\nInstall the package:\n\n"
        "```bash\n" + pc["install_cmd"] + " " + pkg + "\n```\n\n"
        "## Key Capabilities\n\n" + foss + " for " + pc["human"] + " lets you work with " + title.lower() + " programmatically without external dependencies.\n\n"
        "## Learn More\n\n- [Developer Guide](https://docs.aspose.org/" + fam + "/" + plat + "/developer-guide/)\n"
        "- [API Reference](https://reference.aspose.org/" + fam + "/" + plat + "/)\n"
        "- [Knowledge Base](https://kb.aspose.org/" + fam + "/" + plat + "/)\n"
    )


def main():
    missing = []
    for fam in ["3d", "cells", "email", "font", "note", "slides", "words"]:
        fam_dir = "reports/plans/" + fam
        if not os.path.isdir(fam_dir):
            continue
        for plat in os.listdir(fam_dir):
            plan_path = fam_dir + "/" + plat + "/site_plan.yaml"
            if not os.path.isfile(plan_path):
                continue
            with open(plan_path) as f:
                plan = yaml.safe_load(f)
            plan_data = plan.get("plan", plan)
            sections = plan_data.get("sections", {})
            for site, section_data in sections.items():
                pages = section_data.get("pages", []) if isinstance(section_data, dict) else []
                for page in pages:
                    path = page.get("path", "")
                    if path and not os.path.exists(path):
                        missing.append({
                            "family": fam, "platform": plat, "site": site,
                            "path": path, "slug": page.get("slug", ""),
                            "weight": page.get("weight", 100),
                            "cluster": page.get("cluster", ""),
                        })

    api_cache, sha_cache = {}, {}
    created, errors = 0, 0
    for pi in missing:
        key = pi["family"] + "/" + pi["platform"]
        if key not in api_cache:
            api_cache[key] = load_api_surface(pi["family"], pi["platform"])
            sha_cache[key] = load_model_sha(pi["family"], pi["platform"])
        api = api_cache[key]
        sha = sha_cache[key]
        path = pi["path"]
        site = pi["site"]
        try:
            if site == "docs":
                content = gen_docs(pi, api, sha)
            elif site == "kb":
                content = gen_kb(pi, api, sha)
            elif site == "blog":
                content = gen_blog(pi, api, sha)
            else:
                print("SKIP: unknown site " + site + " for " + path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            created += 1
            print("CREATED: " + path)
        except Exception as e:
            errors += 1
            print("ERROR: " + path + ": " + str(e))
    print("\nSummary: " + str(created) + " created, " + str(errors) + " errors, " + str(len(missing)) + " total")


if __name__ == "__main__":
    main()
