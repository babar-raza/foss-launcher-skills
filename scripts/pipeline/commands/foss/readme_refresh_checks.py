"""CONTRACT: deterministic checks for the /readme-refresh skill (plan:
C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md).

Currently implements check_diagram_connectivity() only — the "At a glance" Mermaid
flowchart orphan-node check described in the plan's "Deterministic connectivity
checker" section. Other checks (compute_link_caps, count_aspose_links,
check_enterprise_edition_naming, check_required_sections, surgical_diff_check) are
specified in the plan but not yet implemented; this module grows into the skill's
full checks module as those land.

check_diagram_connectivity parses the ```mermaid flowchart``` block in a README,
classifies each `subgraph` by its label (Inputs / Capabilities / Outputs), and
verifies every node declared inside the Capabilities subgraph has a path (via the
diagram's edges) to at least one node in the Outputs subgraph. A capability node
with no such path is an "orphan" -- the diagram visually claims the capability
exists but never shows it producing anything.

This check is purely structural. It cannot tell whether a node's claim is true
(fabricated node) or stale (correct at generation time, false after a later
correction) -- those require comparing against the README's own Key Capabilities /
Scope and limitations sections and the paired upstream-issues.md, which stays
agent judgment, not a script.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
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


def _classify_subgraph(label: str) -> str | None:
    if not label:
        return None
    lower = label.lower()
    if "input" in lower:
        return "inputs"
    if "capabilit" in lower:
        return "capabilities"
    if "output" in lower:
        return "outputs"
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
            current_kind = _classify_subgraph(start_match.group(2) or "")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check At-a-glance Mermaid diagram connectivity (orphaned Capabilities nodes)."
    )
    parser.add_argument("readme_path", help="Path to a readme.md file")
    args = parser.parse_args(argv)

    with open(args.readme_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    orphans = check_diagram_connectivity(text)
    if not orphans:
        print(f"PASS: {args.readme_path} -- no orphaned capability nodes")
        return 0

    print(f"FAIL: {args.readme_path} -- {len(orphans)} orphaned capability node(s):")
    for orphan in orphans:
        print(f"  {orphan['node_id']}: {orphan['label']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
