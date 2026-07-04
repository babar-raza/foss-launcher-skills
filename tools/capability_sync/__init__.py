"""tools/capability_sync — Unified cross-agent capability synchronization tooling.

This package provides deterministic, idempotent tooling to:
  - Inventory capabilities from skills/registry.yaml
  - Validate semantic parity across all agent adapter surfaces
  - Detect drift between canonical contracts and deployed adapters
  - Generate Claude command and agent skill adapters
  - Detect orphan adapters (no canonical capability)
  - Generate capability discovery indexes for agent instruction files
  - Validate discoverability from each agent's entry point

Main entry point:
    python tools/capability_sync/run_sync.py [--check | --sync]

Individual tools can also be run independently with --check or --sync modes.
"""

__version__ = "1.0.0"
