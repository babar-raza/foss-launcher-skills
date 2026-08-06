"""CONTRACT: deterministic checks for the /readme-refresh skill (plan:
C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md).

Full checks module for the /readme-refresh skill (S-ID assigned at registration; see
skills/readme-refresh.md), called from readme_refresh_run.py's ingest-candidate/recheck/push
subcommands. Two tiers throughout, consistent across every function below:
  - HARD GATE: a non-empty/True result blocks the state-machine transition. Used only where
    the check is genuinely unambiguous (a link target either exists on disk or doesn't; a
    command either matches upstream-issues.md's exact BLOCKING text or doesn't).
  - HEURISTIC / TWO-TIER: a non-empty result is a prompt for the mandatory human/agent
    judgment pass, never an automatic fail. Used wherever "is this actually a problem" is a
    content-quality judgment call a script can't fully automate (tone, member-list accuracy,
    diagram node duplication).

Diagram checks (Mermaid "## At a glance" flowchart, all real, implemented, hard-gate or
heuristic per function): check_diagram_connectivity() [hard gate], check_diagram_known_
subgraph_ids() [heuristic], check_diagram_matches_capability_dependencies() [hard gate once a
product has a data/diagram_capability_dependencies.json entry], check_diagram_suspicious_
direct_product_edge() [heuristic], check_diagram_capability_unreachable_from_product()
[heuristic], check_diagram_no_mechanism_duplicate_output() [heuristic], and check_only_
mermaid_block_changed() [hard gate for mermaid-only refresh runs].

Content checks (whole-README, all real, implemented): compute_link_caps(), count_aspose_
links(), check_enterprise_edition_naming() [heuristic], check_required_sections() [hard gate],
surgical_diff_check() [hard gate], check_license_link_target() [hard gate], check_process_
narration_smells() [heuristic], check_no_undisclosed_blocking_commands() [hard gate],
check_dropped_content() [hard gate at ingest-candidate -- a flagged item needs an explicit
disposition in dropped_claims.json before the transition can pass], check_no_excluded_domain_
links() [hard gate], check_named_member_accuracy() [heuristic -- see its own docstring for an
honest statement of what this heuristic implementation can and cannot verify, versus the
full per-language compiler-grade extraction the plan's Verification pass section describes],
check_api_reference_intro_names_classes() [heuristic].

check_diagram_matches_capability_dependencies (spec'd 2026-08-06, plan section
"Capability-dependency edges") is a hard gate once a product has a recorded
pipeline_edges list (data/diagram_capability_dependencies.json) -- a no-op,
always-pass when pipeline_edges is None (nothing recorded to contradict).
Compares the drawn diagram's edges against the recorded [from, to] pairs:
every recorded pair must have a real from---to edge, `to` must not also carry
a direct PRODUCT---to edge (the barcode/python C5/C6 contradiction this exists
to catch), and any drawn Capability-to-Capability edge absent from the record
is flagged as undeclared (either a real find not yet recorded, or drift).

check_diagram_suspicious_direct_product_edge and
check_diagram_capability_unreachable_from_product (both spec'd 2026-08-06) are
heuristic, non-blocking tripwires. The former flags a Capabilities node wired
both directly from PRODUCT and from a sibling Capability -- the contradictory
double-path shape found live in barcode/python's 2026-08-05 fix (honest recall:
catches only defects with *some* existing Capability-to-Capability edge to
contradict, not the far more common "edge simply never drawn" shape). The
latter flags a Capabilities node with zero inbound edges from PRODUCT or a
sibling Capability -- a regression tripwire for future edits, harmless no-op
against pre-fix diagrams.

check_only_mermaid_block_changed (spec'd 2026-08-06, "Hardened design" section
-- the mermaid-only-refresh enforcement mechanism) extracts the full fenced
```mermaid ... ``` block (fences included) from both an old and new copy of a
README, replaces it with a fixed placeholder in each, and asserts the
remainder is byte-identical. This is the mechanical gate for "a diagram
refresh must touch only the diagram" -- it exists specifically because no
such mechanism existed anywhere in this repo before, and this session already
observed 5 of 8 parallel agents pick up a contaminated pre-edit snapshot once
(a different, complementary risk this check does not itself prevent -- it
only catches a bad *result*, not a bad starting snapshot).

check_diagram_known_subgraph_ids (spec'd 2026-08-06, plan section "Archetype-aware
structure and content rules") is a non-blocking tripwire: flags any `## At a glance`
subgraph ID outside the canonical set {Inputs, FromScratch, Capabilities, Outputs}
-- either a typo'd canonical ID or a genuinely new archetype shape not yet added to
the canonical set. check_diagram_connectivity's ID-based classifier (below) is a
strict allow-list, so an unrecognized ID would otherwise silently drop out of
connectivity checking rather than erroring; this check exists specifically to
surface that silent-drop case for human/agent judgment, never an automatic fail.

check_diagram_no_mechanism_duplicate_output (spec'd 2026-08-05, plan section
"Never split one output artifact into multiple Output nodes purely by
delivery mechanism") is a heuristic pre-filter, two-tier like the other
2026-08-05 checks: it flags any pair of `## At a glance` Output nodes whose
labels share a significant word and where at least one label contains a
delivery-mechanism keyword (path/stream/buffer/bytes/in-memory/file) while
their inbound Capability-edge sets differ. Found live via direct user review
of cells/cpp's rendered GitHub diagram: `.xlsx workbook (path)` and `.xlsx
workbook (binary stream)` were split into two Output nodes, but the stream
variant was wired from only 1 of 5 Capability nodes, falsely implying only
that one capability's work could be stream-saved -- when in reality path vs.
stream is an orthogonal Save() I/O mechanism, unrelated to which capability
populated the workbook. cells/rust had the same defect, worse (3 delivery
variants, 2 gated to a single capability). A portfolio-wide mechanical
pre-filter + manual review confirmed these were the only 2 of 30 files with
this exact defect -- several near-misses (3d/net, cells/python, email/cpp,
email/net, email/python) were checked and confirmed to be genuinely
different output *content*, not mechanism duplicates, and correctly left
alone. A hit is a prompt for the mandatory judgment pass ("same artifact,
different mechanism" vs. "genuinely different content"), never an automatic
fail.

check_api_reference_intro_names_classes (spec'd 2026-08-05, plan section "API
reference intro sentence must name real hub classes") is a cheap regex
tripwire, two-tier like check_process_narration_smells: it flags the
"## API reference" intro sentence (the text between the H2 heading and its
`<details>` fold) when it matches either confirmed bad form -- a bare
"ships N public types. Selected entry points:" filler, or a bare
`namespace.*`/`package.*` wildcard with no backtick-quoted class name in the
same sentence -- as a prompt for the mandatory judgment pass to rewrite it
naming the product's real hub class(es), never an automatic fail (naming a
real hub class is a content-quality judgment call, not mechanically
decidable). Found live on direct user review of 3d/net's rendered GitHub PR
page: the section read as nearly empty (one generic sentence, then everything
real hidden behind a single `<details>` fold with zero class names visible).
A read-only 30-file survey run in response confirmed this is inconsistent
portfolio-wide, not a 3d/net-specific defect -- 9 of 30 files have the weak
pattern (3d/net, pdf/net, cells/net, 3d/java, cells/java, slides/java,
email/net, note/python, 3d/python) while the other 21 already name real hub
classes correctly (e.g. cells/cpp: "The primary entry point is `Workbook`,
which owns a `WorksheetCollection` of `Worksheet` objects.").

check_named_member_accuracy (spec'd 2026-08-05, plan section "Named-member API
claims must be individually verified against real source") is the newest spec'd
check -- it targets a defect class check_dropped_content cannot see: a README
bullet of the form "`ClassName` -- `member1`, `member2`, ..." can name a real,
present class while still listing a wrong member set (a member that doesn't
exist on the real class, or a combined Load/Save-style bullet that's silently
just one side's property list). This was found live in 3d/python's "Format
load/save options" API reference subsection -- ObjSaveOptions had 5 real
Save-only properties silently missing from a combined bullet, and a glTF bullet
claimed an `export_textures` property that exists on neither real class.
check_dropped_content only tests presence (does old topic X still appear
somewhere); this checks accuracy (is the specific technical claim about a
present topic actually true of the real source) -- a different failure mode
needing a different check, not wider coverage of the same one.

check_diagram_connectivity parses the ```mermaid flowchart``` block in a README,
classifies each `subgraph` by its ID (Inputs / FromScratch / Capabilities / Outputs
-- changed 2026-08-06 from classifying by label text, see below), and verifies
every node declared inside the Capabilities subgraph has a path (via the diagram's
edges) to at least one node in the Outputs subgraph. A capability node with no such
path is an "orphan" -- the diagram visually claims the capability exists but never
shows it producing anything.

This check is purely structural. It cannot tell whether a node's claim is true
(fabricated node) or stale (correct at generation time, false after a later
correction) -- those require comparing against the README's own Key Capabilities /
Scope and limitations sections and the paired upstream-issues.md, which stays
agent judgment, not a script.

ID-based classification (2026-08-06): originally this classified by matching
substrings ("input"/"capabilit"/"output") in the subgraph's display LABEL text.
That stopped being a safe signal once the plan's archetype system (Template
section, "Archetype-aware structure and content rules") started allowing display
labels to vary per product archetype -- e.g. a generative product's Inputs
subgraph is titled "Input data and options", not "Inputs and formats". The
subgraph ID (`subgraph Inputs[...]` -- the bare word before the `[`) stays a
stable, non-prose anchor regardless of what the label says, so classification now
keys off group(1) (the ID) instead of group(2) (the label). Verified backward
compatible against the full 30-file corpus before this landed: every existing
diagram already writes an ID that equals its own label text verbatim, so this is
a no-op for all pre-existing files. `Inputs` and `FromScratch` (the new subgraph
a hybrid-archetype product's diagram may add, per the Template section) are both
classified into a single "source" bucket -- the connectivity check's BFS logic
never enumerated Inputs subgraphs in the first place (it only walks forward from
Capabilities to Outputs), so folding FromScratch into the same bucket needed no
change to that logic, only to classification.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field

_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
_MERMAID_BLOCK_FULL_RE = re.compile(r"```mermaid\s*\n.*?```", re.DOTALL)
_MERMAID_BLOCK_PLACEHOLDER = "```mermaid\n<MERMAID_BLOCK_CHECKED_SEPARATELY>\n```"
_SUBGRAPH_START_RE = re.compile(r'^\s*subgraph\s+([A-Za-z0-9_]+)(?:\["(.*?)"\])?\s*$')
_SUBGRAPH_END_RE = re.compile(r"^\s*end\s*$")
_NODE_DECL_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*\["(.*?)"\]\s*$')
_EDGE_RE = re.compile(
    r'^\s*([A-Za-z0-9_]+)\s*(?:\["(.*?)"\])?\s*-{1,3}>?\s*([A-Za-z0-9_]+)\s*(?:\["(.*?)"\])?\s*$'
)


@dataclass
class DiagramGraph:
    node_subgraph: dict = field(default_factory=dict)  # node_id -> subgraph kind
    node_label: dict = field(default_factory=dict)  # node_id -> label text
    edges: list = field(default_factory=list)  # list of (a, b)
    subgraph_kinds_seen: set = field(default_factory=set)


_SOURCE_IDS = {"Inputs", "FromScratch"}
_CANONICAL_SUBGRAPH_IDS = _SOURCE_IDS | {"Capabilities", "Outputs"}


def _classify_subgraph(subgraph_id: str) -> str | None:
    if not subgraph_id:
        return None
    if subgraph_id == "Capabilities":
        return "capabilities"
    if subgraph_id == "Outputs":
        return "outputs"
    if subgraph_id in _SOURCE_IDS:
        return "source"
    return None


def extract_mermaid_block(markdown_text: str) -> str | None:
    match = _MERMAID_BLOCK_RE.search(markdown_text)
    if not match:
        return None
    return match.group(1)


def parse_diagram(mermaid_text: str) -> DiagramGraph:
    graph = DiagramGraph()
    current_kind: str | None = None

    for raw_line in mermaid_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("flowchart"):
            continue

        start_match = _SUBGRAPH_START_RE.match(line)
        if start_match:
            current_kind = _classify_subgraph(start_match.group(1))
            if current_kind:
                graph.subgraph_kinds_seen.add(current_kind)
            continue

        if _SUBGRAPH_END_RE.match(line):
            current_kind = None
            continue

        node_match = _NODE_DECL_RE.match(line)
        if node_match:
            node_id, label = node_match.group(1), node_match.group(2)
            graph.node_label[node_id] = label
            if current_kind:
                graph.node_subgraph[node_id] = current_kind
            continue

        edge_match = _EDGE_RE.match(line)
        if edge_match:
            a, a_label, b, b_label = edge_match.groups()
            if a_label:
                graph.node_label.setdefault(a, a_label)
            if b_label:
                graph.node_label.setdefault(b, b_label)
            graph.edges.append((a, b))
            continue
        # Anything else (comments, styling directives) is ignored -- not our concern.

    return graph


def _bfs_reaches_kind(graph: DiagramGraph, start: str, target_kind: str) -> bool:
    # Directed reachability, following edges only in the direction they're written
    # (left operand -> right operand). This matches the diagrams' left-to-right
    # flow semantics (Input -> PRODUCT -> Capability -> Output). An UNDIRECTED
    # graph would be wrong here: PRODUCT is a shared hub every Input/Capability
    # connects to, so undirected BFS would call every node "reachable" from every
    # other node through PRODUCT regardless of real downstream connectivity.
    adjacency: dict[str, list[str]] = {}
    for a, b in graph.edges:
        adjacency.setdefault(a, []).append(b)

    seen = {start}
    queue = [start]
    while queue:
        node = queue.pop(0)
        if graph.node_subgraph.get(node) == target_kind:
            return True
        for neighbor in adjacency.get(node, []):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def check_diagram_connectivity(markdown_text: str) -> list[dict]:
    """Return a list of orphan findings: [{"node_id", "label"}], empty if none.

    Each finding is a Capabilities-subgraph node with no path to any
    Outputs-subgraph node. Returns [] if there's no mermaid block, or no
    recognized Capabilities/Outputs subgraphs (nothing to check).
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []

    graph = parse_diagram(mermaid_text)
    if "capabilities" not in graph.subgraph_kinds_seen or "outputs" not in graph.subgraph_kinds_seen:
        return []

    orphans = []
    for node_id, kind in graph.node_subgraph.items():
        if kind != "capabilities":
            continue
        if not _bfs_reaches_kind(graph, node_id, "outputs"):
            orphans.append({"node_id": node_id, "label": graph.node_label.get(node_id, "")})
    return orphans


def check_diagram_known_subgraph_ids(markdown_text: str) -> list[str]:
    """Return any `## At a glance` subgraph IDs outside the canonical set.

    Canonical set: {Inputs, FromScratch, Capabilities, Outputs}. A non-blocking
    tripwire -- an unrecognized ID is either a typo'd canonical ID or a
    genuinely new archetype shape not yet added to the canonical set, and
    since check_diagram_connectivity's classifier is a strict allow-list, an
    unrecognized ID would otherwise silently drop out of connectivity
    checking instead of erroring. Returns [] if there's no mermaid block.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []

    unknown = []
    for raw_line in mermaid_text.splitlines():
        match = _SUBGRAPH_START_RE.match(raw_line.strip())
        if match and match.group(1) not in _CANONICAL_SUBGRAPH_IDS:
            unknown.append(match.group(1))
    return unknown


def check_diagram_matches_capability_dependencies(
    markdown_text: str, pipeline_edges: list[list[str]] | None
) -> list[dict]:
    """Compare the drawn diagram's edges against a recorded pipeline_edges list.

    `pipeline_edges` is the `[[from_capability_id, to_capability_id], ...]` value
    from a product's `data/diagram_capability_dependencies.json` entry, or None
    if that product has no entry at all -- absence means "never traced", never
    "confirmed independent" (the opposite convention from diagram_archetypes.json),
    so None always returns [] (a no-op, correctly, since there's nothing recorded
    to contradict). An empty list ([]) means "traced, confirmed no dependencies" --
    a real, positive record -- and IS checked (against undeclared C-to-C edges).

    Findings, each a dict with a "type" key:
      - "missing_edge": a recorded [from, to] pair has no real from---to edge drawn.
      - "contradictory_direct_edge": a recorded pair's `to` node also carries a
        direct PRODUCT---to edge (the barcode/python C5/C6 shape).
      - "undeclared_edge": a drawn Capability-to-Capability edge not present in
        the recorded pipeline_edges (either a real find not yet recorded, or drift).
    """
    if pipeline_edges is None:
        return []

    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []

    graph = parse_diagram(mermaid_text)
    drawn_edges = set(graph.edges)
    recorded_pairs = {(pair[0], pair[1]) for pair in pipeline_edges}

    findings: list[dict] = []
    contradicted_targets: set[str] = set()
    for from_id, to_id in recorded_pairs:
        if (from_id, to_id) not in drawn_edges:
            findings.append(
                {"type": "missing_edge", "from": from_id, "to": to_id}
            )
        if ("PRODUCT", to_id) in drawn_edges and to_id not in contradicted_targets:
            contradicted_targets.add(to_id)
            findings.append(
                {"type": "contradictory_direct_edge", "from": "PRODUCT", "to": to_id}
            )

    for a, b in graph.edges:
        if graph.node_subgraph.get(a) != "capabilities":
            continue
        if graph.node_subgraph.get(b) != "capabilities":
            continue
        if (a, b) not in recorded_pairs:
            findings.append({"type": "undeclared_edge", "from": a, "to": b})

    return findings


def check_diagram_suspicious_direct_product_edge(markdown_text: str) -> list[dict]:
    """Flag a Capabilities node wired both directly from PRODUCT and from a sibling.

    Heuristic, non-blocking. Honest recall: catches only the shape where *some*
    Capability-to-Capability edge already exists to contradict (barcode/python's
    C5, uniquely among the pre-fix corpus). Misses the far more common "the
    correct edge was simply never drawn" shape (barcode's C6, both tex/python
    cases, email/python's C6) -- a clean pass here must never be read as
    "verified", only "no contradiction of this specific shape found".
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []

    graph = parse_diagram(mermaid_text)
    findings = []
    for node_id, kind in graph.node_subgraph.items():
        if kind != "capabilities":
            continue
        has_direct_product_edge = ("PRODUCT", node_id) in graph.edges
        has_sibling_edge = any(
            b == node_id and graph.node_subgraph.get(a) == "capabilities"
            for a, b in graph.edges
        )
        if has_direct_product_edge and has_sibling_edge:
            findings.append({"node_id": node_id, "label": graph.node_label.get(node_id, "")})
    return findings


def check_diagram_capability_unreachable_from_product(markdown_text: str) -> list[dict]:
    """Flag a Capabilities node with zero inbound edges from PRODUCT or a sibling.

    Heuristic, non-blocking. Harmless no-op against a pre-Rule-1-fix diagram
    (every node still has its PRODUCT edge); becomes load-bearing as Direct-edge
    fixes land and start replacing PRODUCT edges with Capability-to-Capability
    edges, catching the slip of deleting a PRODUCT edge without wiring the
    real upstream Capability in its place.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []

    graph = parse_diagram(mermaid_text)
    findings = []
    for node_id, kind in graph.node_subgraph.items():
        if kind != "capabilities":
            continue
        has_inbound = any(
            b == node_id and (a == "PRODUCT" or graph.node_subgraph.get(a) == "capabilities")
            for a, b in graph.edges
        )
        if not has_inbound:
            findings.append({"node_id": node_id, "label": graph.node_label.get(node_id, "")})
    return findings


def check_only_mermaid_block_changed(old_markdown_text: str, new_markdown_text: str) -> bool:
    """Return True iff the only difference between old and new is inside the
    ```mermaid ... ``` fenced block (fences included).

    Both texts have their fenced mermaid block (if any) replaced with an
    identical fixed placeholder, then compared for exact equality. If a text
    has no mermaid block, the placeholder substitution is a no-op for it --
    so a mermaid block appearing/disappearing between old and new correctly
    fails this check (that is not "only the diagram changed").
    """
    old_stripped = _MERMAID_BLOCK_FULL_RE.sub(_MERMAID_BLOCK_PLACEHOLDER, old_markdown_text, count=1)
    new_stripped = _MERMAID_BLOCK_FULL_RE.sub(_MERMAID_BLOCK_PLACEHOLDER, new_markdown_text, count=1)
    return old_stripped == new_stripped


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
# "Additional examples" deliberately excluded: the Template section makes it vacuously
# optional ("If a product has no 'Additional examples' section at all (too few real snippets
# to justify one), this requirement is vacuously satisfied") -- confirmed real, not
# hypothetical: cells/cpp is the one product in the current 30-file portfolio with no such
# section, and it is not a defect. "Enough real snippets to justify one" is a content-quality
# judgment call this check cannot responsibly automate, so it stays outside the hard gate.
_REQUIRED_SECTIONS = [
    "At a glance",
    "Key capabilities",
    "Installation",
    "Quick start",
    "API reference",
    "Documentation & resources",
    "Scope and limitations",
    "Development and testing",
    "License",
]
_ASPOSE_LINK_HOST_RE = re.compile(r"https?://(?:[\w-]+\.)*aspose\.(?:org|com)\b")
_ENTERPRISE_LINK_HOST_RE = re.compile(r"https?://(?:[\w-]+\.)*products\.aspose\.com\b")


def compute_link_caps(readme_text: str) -> dict:
    """Count markdown links by category for the link-density-ceiling rule (Template section,
    "no repeated Enterprise mention... to respect the link-density ceiling").

    Returns {"total_links", "aspose_org_links", "enterprise_edition_links",
    "enterprise_edition_link_contexts"} -- the last is a list of ~60-char text snippets
    surrounding each Enterprise link, so a caller can confirm every one is confined to the
    Scope and limitations section without re-parsing the file.
    """
    links = _MD_LINK_RE.findall(readme_text)
    total = len(links)
    aspose_org = sum(1 for _, href in links if _ASPOSE_LINK_HOST_RE.search(href))
    enterprise_contexts = []
    for match in re.finditer(_MD_LINK_RE, readme_text):
        href = match.group(2)
        if _ENTERPRISE_LINK_HOST_RE.search(href):
            start = max(0, match.start() - 30)
            end = min(len(readme_text), match.end() + 30)
            enterprise_contexts.append(readme_text[start:end].replace("\n", " "))
    return {
        "total_links": total,
        "aspose_org_links": aspose_org,
        "enterprise_edition_links": len(enterprise_contexts),
        "enterprise_edition_link_contexts": enterprise_contexts,
    }


def count_aspose_links(readme_text: str) -> int:
    """Count markdown links whose href targets an aspose.org or aspose.com subdomain."""
    return sum(
        1 for _, href in _MD_LINK_RE.findall(readme_text) if _ASPOSE_LINK_HOST_RE.search(href)
    )


def check_enterprise_edition_naming(readme_text: str) -> list[dict]:
    """Flag any products.aspose.com link whose visible anchor text doesn't contain
    "Enterprise Edition" -- the plan's own established naming convention (deliberately not
    backlink_targets.py's "Enterprise Product"/"Enterprise Product Family" phrasing, which is
    a different convention for a different consumer). Heuristic: a hit is a prompt for review,
    since a handful of legitimate phrasings ("...for the Enterprise Edition of...") may still
    satisfy intent without matching the literal substring check here.
    """
    findings = []
    for match in _MD_LINK_RE.finditer(readme_text):
        anchor_text, href = match.group(1), match.group(2)
        if _ENTERPRISE_LINK_HOST_RE.search(href) and "Enterprise Edition" not in anchor_text:
            findings.append({"anchor_text": anchor_text, "href": href})
    return findings


def check_required_sections(readme_text: str) -> list[str]:
    """Return the list of required H2 section names missing from the README. Hard gate --
    every product's candidate must carry the full Template section list, always."""
    missing = []
    for section in _REQUIRED_SECTIONS:
        if not re.search(rf"^##\s+{re.escape(section)}\s*$", readme_text, re.MULTILINE):
            missing.append(section)
    return missing


def surgical_diff_check(declared_file_set: list[str], changed_files: list[str]) -> list[str]:
    """Return any path in changed_files not present in declared_file_set -- an undeclared
    change. Hard gate at push time: the file set is fixed at plan time and shown during
    review (Design section, "surgical_diff_check (declared file-set only...)"); anything
    outside it must never silently ride along in the same push.
    """
    declared = set(declared_file_set)
    return [path for path in changed_files if path not in declared]


def check_license_link_target(readme_text: str, clone_cache_root: str) -> list[dict]:
    """Verify the ## License section's link target (if any) exists on disk, case-sensitively,
    under clone_cache_root. Hard gate -- catches both a fabricated path (words/python's real
    License/license.txt vs the candidate's claimed License/license.txt casing/name mismatch)
    and a missing-license-file case that should carry no link at all (3d/typescript).

    Returns [] when the section either has no link (plain-text "MIT License", the correct
    form when no license file exists) or the linked path resolves case-sensitively on disk.
    Returns a one-item list with the bad target when the link is present but doesn't resolve.
    """
    license_match = re.search(r"^##\s+License\s*$(.*?)(?=^##\s|\Z)", readme_text, re.MULTILINE | re.DOTALL)
    if not license_match:
        return []
    section_text = license_match.group(1)
    link_match = _MD_LINK_RE.search(section_text)
    if not link_match:
        return []
    target = link_match.group(2)
    if target.startswith(("http://", "https://")):
        return []
    root = Path(clone_cache_root)
    candidate = root / target
    if candidate.is_file():
        try:
            real_name = next(p.name for p in candidate.parent.iterdir() if p.name == candidate.name)
        except StopIteration:
            real_name = None
        if real_name != candidate.name:
            return [{"target": target, "reason": "case mismatch on disk"}]
        return []
    return [{"target": target, "reason": "target does not exist under clone cache"}]


_PROCESS_NARRATION_PATTERNS = [
    r"\bat the time of writing\b",
    r"\bas of this writing\b",
    r"\bconsult the repository directly\b",
    r"\bas declared in\b",
    r"\bseems to\b",
    r"\bpresumably\b",
    r"\bpasses cleanly\b",
    r"\bcurrently fails\b",
    r"\bwas verified\b",
    r"\bverified with\b",
    r"\bverified against\b",
    r"\bconfirmed against this checkout\b",
    r"\bno match under\b",
    r"\bfound directly in source\b",
    r"\breproduced independently\b",
    r"\bthis reproduces with\b",
    r"\bfails identically\b",
    r"\breproduced from its own\b",
    r"\bthe upstream repository'?s own\b",
    r"\bthe source repository\b",
    r"\(per the\b",
    r"\bwithout obscuring the primary\b",
]
_PROCESS_NARRATION_RE = re.compile("|".join(_PROCESS_NARRATION_PATTERNS), re.IGNORECASE)


def check_process_narration_smells(readme_text: str) -> list[dict]:
    """Flag sentences narrating the generation/verification *process* instead of stating a
    product fact (Template section, "No process/investigation-log narration anywhere in the
    README"). Heuristic, cheap regex tripwire feeding the mandatory tone-review judgment pass
    during verify-examples -- a hit is a prompt to look, never an automatic fail (a plain
    present-tense limitation sentence in Scope and limitations is fine; the smell is the
    audit-trail *voice*, not the presence of a caveat).
    """
    findings = []
    for match in _PROCESS_NARRATION_RE.finditer(readme_text):
        start = max(0, match.start() - 40)
        end = min(len(readme_text), match.end() + 40)
        findings.append({"phrase": match.group(0), "context": readme_text[start:end].replace("\n", " ")})
    return findings


_FENCED_CODE_RE = re.compile(r"```(?:bash|sh|shell|powershell|cmd)?\n(.*?)```", re.DOTALL)
_BLOCKING_ISSUE_RE = re.compile(
    r"-\s+\*\*Severity\*\*:\s*BLOCKING.*?-\s+\*\*Evidence\*\*:\s*(.+?)\n",
    re.DOTALL,
)


def check_no_undisclosed_blocking_commands(readme_text: str, upstream_issues_text: str) -> list[dict]:
    """Cross-check every fenced install/build command in the README against upstream-issues.md's
    BLOCKING-severity entries for that exact command. Hard gate -- the html/python and words/net
    incidents (a documented BLOCKING command shipped as the standard Installation step, with no
    warning) were a correctness/safety defect, not a style one, so this one blocks the
    transition rather than just prompting review.
    """
    blocking_commands = []
    for match in _BLOCKING_ISSUE_RE.finditer(upstream_issues_text):
        evidence = match.group(1).strip().strip("`")
        blocking_commands.append(evidence)
    if not blocking_commands:
        return []
    findings = []
    for code_match in _FENCED_CODE_RE.finditer(readme_text):
        block = code_match.group(1)
        for blocking_cmd in blocking_commands:
            if blocking_cmd and blocking_cmd in block:
                findings.append({"command": blocking_cmd, "block": block.strip()})
    return findings


_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)


def check_dropped_content(old_readme_text: str, new_readme_text: str, clone_cache_root: str) -> dict:
    """Diff the old (upstream) README against the new candidate for links and H2/H3 headings
    present in the old file with no match anywhere in the new one. Hard gate at
    ingest-candidate -- a flagged item needs an explicit disposition in dropped_claims.json
    (carried forward / dropped with a verified reason) before the transition can pass, per
    the "Never drop original-README content without a verified reason" rule.

    Returns {"dropped_links": [...], "dropped_headings": [...]}. A link is "dropped" only if
    its exact target string doesn't appear anywhere in new_readme_text (a real move to a
    different section still counts as carried forward, correctly). clone_cache_root is
    accepted for API-shape parity with check_license_link_target (a caller may wish to filter
    out links to files that no longer exist upstream either) but this heuristic-diff pass does
    not itself require it to detect a drop.
    """
    del clone_cache_root  # accepted for signature parity; presence-diffing needs only the two texts
    old_links = {href for _, href in _MD_LINK_RE.findall(old_readme_text) if not href.startswith(("http://", "https://"))}
    dropped_links = sorted(href for href in old_links if href not in new_readme_text)

    old_headings = {m.group(2) for m in _HEADING_RE.finditer(old_readme_text)}
    new_headings_and_body = new_readme_text
    dropped_headings = sorted(h for h in old_headings if h not in new_headings_and_body)

    return {"dropped_links": dropped_links, "dropped_headings": dropped_headings}


_EXCLUDED_DOMAINS_RE = re.compile(r"https?://(?:[\w-]+\.)*(?:forum\.aspose\.com|[\w-]+\.aspose\.app)\b")


def check_no_excluded_domain_links(readme_text: str) -> list[str]:
    """Hard gate: reject any link whose host is forum.aspose.com or matches *.aspose.app --
    a standing policy ("we will not link to forum.aspose.com or any subdomain at aspose.app
    at this stage"), not a per-run judgment call. Returns the list of matched URLs.
    """
    return [m.group(0) for m in _EXCLUDED_DOMAINS_RE.finditer(readme_text)]


_CLASS_BULLET_RE = re.compile(
    r"^(?P<indent> *)-\s+`([A-Za-z_][\w.]*)`(?:\s*/\s*`([A-Za-z_][\w.]*)`)?(?:\s*[—-]+.*)?$",
    re.MULTILINE,
)
_BACKTICK_MEMBER_RE = re.compile(r"`([A-Za-z_]\w*(?:\([^)]*\))?)`")
_SUB_BULLET_LINE_RE = re.compile(r"^ +-\s+(.+)$")


def check_named_member_accuracy(readme_text: str, clone_cache_root: str) -> list[dict]:
    """Heuristic accuracy check for the API reference's real on-disk bullet convention: a
    top-level `` - `ClassName` [— description] `` bullet followed by zero or more MORE-INDENTED
    sub-bullet lines listing that class's real members (either one signature per line, e.g.
    `` - `create(subject, body) -> "MapiMessage"` ``, or a single `properties: `a`, `b`, `c`
    ``-style comma line) -- does every member named in those sub-bullets plausibly exist on the
    named class's real source?

    Deliberately does NOT treat a bare single-line "`ClassName` — prose mentioning `a_term()`"
    bullet (no indented sub-bullets following it, e.g. an Exceptions-list one-liner) as a
    member-list claim -- confirmed via a real false-positive during this function's own
    development (barcode/python's "`SymbologyNotFoundError` — unknown symbology name passed to
    `generate()`" is a description, not a claim that `generate()` is SymbologyNotFoundError's
    own member; only genuinely indented sub-bullets count as the member list).

    HONEST SCOPE STATEMENT (do not treat a clean pass from this function as compiler-grade
    proof): this is a grep-based heuristic, not the full per-language extraction the plan's
    Verification pass section describes (`javap -public` for Java, real introspection for
    Python, compiler diagnostics for C#/Go/Rust/C++, `tsc` for TypeScript). It locates
    candidate source files for a named class via a simple `class ClassName`/`struct
    ClassName`/`interface ClassName` grep across clone_cache_root, then checks whether each
    named member token appears anywhere in that file's text. This can miss real member-name
    typos hidden by fuzzy matching, can under-report on classes split across multiple files
    (partial classes, extension methods, trait impls), and does NOT trace inheritance -- a
    member declared once on a base class and inherited (confirmed live: words/net's
    `Document.GetText()`, real and callable, declared only on the base `Node` class) will be
    flagged as "not found" even though it's genuinely valid. A member absent from every
    candidate file is a real, worth-flagging signal, but presence in the file text is not proof
    the member is real, public, and matches the exact bullet's claimed shape. Treat every
    finding as a prompt for the same real per-language verification this check cannot fully
    automate, never as a substitute for it.

    Returns a list of {"class_name", "member", "reason"} findings for members not found in any
    candidate source file for their class. Returns [] (not an error) if a class name has zero
    candidate source files -- that's a "couldn't verify" case for the human/agent pass, not a
    fabrication claim this heuristic can respons­ibly make on no evidence.
    """
    root = Path(clone_cache_root)
    if not root.is_dir():
        return []

    lines = readme_text.splitlines()
    findings = []
    for match in _CLASS_BULLET_RE.finditer(readme_text):
        class_a, class_b = match.group(2), match.group(3)
        bullet_indent = len(match.group("indent"))
        bullet_line_idx = readme_text.count("\n", 0, match.start())

        members: list[str] = []
        for line in lines[bullet_line_idx + 1:]:
            sub_match = _SUB_BULLET_LINE_RE.match(line)
            if not sub_match:
                break
            sub_indent = len(line) - len(line.lstrip(" "))
            if sub_indent <= bullet_indent:
                break
            members.extend(_BACKTICK_MEMBER_RE.findall(sub_match.group(1)))
        if not members:
            continue

        for class_name in filter(None, (class_a, class_b)):
            candidate_files = _find_class_source_files(root, class_name)
            if not candidate_files:
                continue  # no evidence either way -- not a fabrication claim, skip silently
            combined_text = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in candidate_files)
            for member in members:
                member_token = member.split("(")[0].split(":")[0].strip()
                if member_token and member_token not in combined_text:
                    findings.append({
                        "class_name": class_name,
                        "member": member,
                        "reason": f"not found in {len(candidate_files)} candidate source file(s)",
                    })
    return findings


def _find_class_source_files(root: Path, class_name: str, max_files: int = 5) -> list[Path]:
    """Locate up to max_files real source files plausibly DEFINING class_name (not merely
    forward-declaring it), via a cheap grep-style scan -- not a real per-language parse.
    Skips common non-source directories.

    The `(?!\\s*;)` negative lookahead is load-bearing, not decorative: a real bug found
    during this function's own development -- `class Worksheet;` forward declarations (C++
    headers routinely forward-declare a type before using it by reference/pointer) matched the
    same naive "class ClassName" regex as the real `class Worksheet final { ... }` definition,
    and since several forward-declaring headers sort alphabetically before the real definition
    file, they filled max_files before the real file was ever reached -- producing false
    "member not found" findings for members that are genuinely declared, just in a file this
    function never got to.
    """
    declare_re = re.compile(
        rf"\b(?:class|struct|interface|def)\s+{re.escape(class_name)}\b(?!\s*;)"
    )
    skip_dirs = {".git", "node_modules", "__pycache__", "target", "build", "dist", "bin", "obj"}
    found: list[Path] = []
    for path in root.rglob("*"):
        if len(found) >= max_files:
            break
        if not path.is_file() or path.suffix not in {
            ".py", ".java", ".cs", ".go", ".rs", ".cpp", ".hpp", ".h", ".ts", ".c"
        }:
            continue
        if skip_dirs & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if declare_re.search(text):
            found.append(path)
    return found


_API_REF_INTRO_BAD_A_RE = re.compile(r"ships \d+ public types\.\s*Selected entry points:", re.IGNORECASE)
_API_REF_INTRO_BAD_B_RE = re.compile(r"`\w[\w.]*\.\*`?\s*\.?\s*$")
_API_REF_SECTION_RE = re.compile(
    r"^##\s+API reference\s*$(.*?)(?=<details>|\Z)", re.MULTILINE | re.DOTALL
)


def check_api_reference_intro_names_classes(readme_text: str) -> bool:
    """Flag the "## API reference" intro sentence (text between the H2 heading and its
    <details> fold) when it matches either confirmed bad form: a bare "ships N public types.
    Selected entry points:" filler, or a bare trailing `namespace.*`/`package.*` wildcard with
    no backtick-quoted class name elsewhere in the sentence. Heuristic -- a hit is a prompt for
    the mandatory judgment pass to rewrite the sentence naming the product's real hub class(es),
    never an automatic fail (naming a real hub class is a content-quality judgment call).
    """
    section_match = _API_REF_SECTION_RE.search(readme_text)
    if not section_match:
        return False
    intro = section_match.group(1)
    if _API_REF_INTRO_BAD_A_RE.search(intro):
        return True
    if _API_REF_INTRO_BAD_B_RE.search(intro.strip()):
        # Only a defect if no OTHER backtick-quoted class name appears earlier in the sentence.
        other_backticks = _BACKTICK_MEMBER_RE.findall(intro)
        if len(other_backticks) <= 1:
            return True
    return False


_DELIVERY_MECHANISM_KEYWORDS_RE = re.compile(
    r"\b(?:path|stream|buffer|bytes|in-memory)\b", re.IGNORECASE
)
_WORD_RE = re.compile(r"[A-Za-z]{4,}")
# Generic/structural nouns that recur across genuinely-different Output labels (".msg files" vs
# ".eml files") -- excluded from "shared significant word" consideration so a coincidental shared
# noun alone never triggers this heuristic; the real 2026-08-05 incidents (cells/cpp, cells/rust)
# shared a specific format token (".xlsx workbook"), not a generic container word.
_GENERIC_LABEL_WORDS = {
    "file", "files", "document", "documents", "object", "objects", "data", "content",
    "contents", "output", "outputs", "format", "formats", "with", "from", "into",
}


def check_diagram_no_mechanism_duplicate_output(markdown_text: str) -> list[dict]:
    """Heuristic pre-filter for the "never split one output artifact into multiple Output
    nodes purely by delivery mechanism" rule (the cells/cpp and cells/rust incident). Flags
    any pair of Outputs-subgraph nodes whose labels share a significant word (>=4 letters) and
    where at least one label contains a delivery-mechanism keyword, while their inbound
    Capability-edge sets differ. A hit prompts the mandatory judgment pass ("same artifact,
    different mechanism" vs. "genuinely different content"), never an automatic fail -- several
    genuinely-different-content near-misses (3d/net's OBJ/STL/glTF vs FBX/COLLADA/3MF pair,
    among others) were checked and correctly left alone during the incident this exists to
    catch, so a hit here is not itself proof of a defect.
    """
    mermaid_text = extract_mermaid_block(markdown_text)
    if mermaid_text is None:
        return []
    graph = parse_diagram(mermaid_text)

    output_nodes = [nid for nid, kind in graph.node_subgraph.items() if kind == "outputs"]
    inbound: dict[str, set] = {nid: set() for nid in output_nodes}
    for a, b in graph.edges:
        if b in inbound:
            inbound[b].add(a)

    findings = []
    for i, node_a in enumerate(output_nodes):
        label_a = graph.node_label.get(node_a, "")
        words_a = {w.lower() for w in _WORD_RE.findall(label_a)} - _GENERIC_LABEL_WORDS
        has_mechanism_a = bool(_DELIVERY_MECHANISM_KEYWORDS_RE.search(label_a))
        for node_b in output_nodes[i + 1:]:
            label_b = graph.node_label.get(node_b, "")
            words_b = {w.lower() for w in _WORD_RE.findall(label_b)} - _GENERIC_LABEL_WORDS
            has_mechanism_b = bool(_DELIVERY_MECHANISM_KEYWORDS_RE.search(label_b))
            shared_words = words_a & words_b
            if shared_words and (has_mechanism_a or has_mechanism_b) and inbound[node_a] != inbound[node_b]:
                findings.append({
                    "node_a": node_a, "label_a": label_a,
                    "node_b": node_b, "label_b": label_b,
                    "shared_words": sorted(shared_words),
                })
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check At-a-glance Mermaid diagram connectivity (orphaned Capabilities nodes)."
    )
    parser.add_argument("readme_path", help="Path to a readme.md file")
    parser.add_argument(
        "--pipeline-edges",
        default=None,
        help=(
            'JSON array of [from, to] capability-id pairs for this product, e.g. '
            '\'[["C1","C5"],["C2","C5"]]\'. Omit for products with no recorded entry '
            "in data/diagram_capability_dependencies.json (the check is a no-op then)."
        ),
    )
    args = parser.parse_args(argv)

    with open(args.readme_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    exit_code = 0

    unknown_ids = check_diagram_known_subgraph_ids(text)
    if unknown_ids:
        print(f"WARN: {args.readme_path} -- unrecognized subgraph ID(s): {', '.join(unknown_ids)}")

    suspicious = check_diagram_suspicious_direct_product_edge(text)
    if suspicious:
        labels = ", ".join(f"{f['node_id']} ({f['label']})" for f in suspicious)
        print(f"WARN: {args.readme_path} -- suspicious direct-PRODUCT-edge node(s): {labels}")

    unreachable = check_diagram_capability_unreachable_from_product(text)
    if unreachable:
        labels = ", ".join(f"{f['node_id']} ({f['label']})" for f in unreachable)
        print(f"WARN: {args.readme_path} -- unreachable-from-PRODUCT node(s): {labels}")

    if args.pipeline_edges is not None:
        pipeline_edges = json.loads(args.pipeline_edges)
        dependency_findings = check_diagram_matches_capability_dependencies(text, pipeline_edges)
        if dependency_findings:
            exit_code = 1
            print(f"FAIL: {args.readme_path} -- {len(dependency_findings)} capability-dependency mismatch(es):")
            for finding in dependency_findings:
                print(f"  {finding['type']}: {finding['from']} -> {finding['to']}")
        else:
            print(f"PASS: {args.readme_path} -- diagram matches recorded capability dependencies")

    orphans = check_diagram_connectivity(text)
    if not orphans:
        print(f"PASS: {args.readme_path} -- no orphaned capability nodes")
        return exit_code

    print(f"FAIL: {args.readme_path} -- {len(orphans)} orphaned capability node(s):")
    for orphan in orphans:
        print(f"  {orphan['node_id']}: {orphan['label']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
