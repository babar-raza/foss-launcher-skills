"""CONTRACT: deterministic checks for the /readme-refresh skill (plan:
C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md).

Currently implements: check_diagram_connectivity(), check_diagram_known_subgraph_ids(),
check_diagram_matches_capability_dependencies(), check_diagram_suspicious_direct_product_edge(),
check_diagram_capability_unreachable_from_product(), and check_only_mermaid_block_changed()
-- all "At a glance" Mermaid flowchart checks. Other checks (compute_link_caps,
count_aspose_links, check_enterprise_edition_naming, check_required_sections,
surgical_diff_check, check_license_link_target, check_process_narration_smells,
check_no_undisclosed_blocking_commands, check_dropped_content,
check_no_excluded_domain_links, check_named_member_accuracy,
check_api_reference_intro_names_classes,
check_diagram_no_mechanism_duplicate_output) are specified in the plan but
not yet implemented; this module grows into the skill's full checks module
as those land.

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
