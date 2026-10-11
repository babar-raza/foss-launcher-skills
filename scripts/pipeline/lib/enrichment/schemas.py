"""schemas.py — JSON schemas for S-98 enrichment output artifacts.

Lightweight schemas for validating coverage matrix, candidate list,
denominator check, and handoff manifest outputs.
"""
from __future__ import annotations

COVERAGE_MATRIX_SCHEMA = {
    "type": "object",
    "required": ["family", "platform", "clusters", "matrix", "summary"],
    "properties": {
        "family": {"type": "string"},
        "platform": {"type": "string"},
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["category", "claim_count"],
                "properties": {
                    "category": {"type": "string"},
                    "claim_count": {"type": "integer", "minimum": 0},
                },
            },
        },
        "matrix": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        "summary": {
            "type": "object",
            "required": ["total_cells", "coverage_ratio"],
            "properties": {
                "total_cells": {"type": "integer", "minimum": 0},
                "coverage_ratio": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
    },
}

CANDIDATE_LIST_SCHEMA = {
    "type": "object",
    "required": ["family", "platform", "candidates", "denominator"],
    "properties": {
        "family": {"type": "string"},
        "platform": {"type": "string"},
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["cluster", "subdomain", "action", "disposition", "score"],
                "properties": {
                    "cluster": {"type": "string"},
                    "subdomain": {"type": "string"},
                    "action": {"type": "string"},
                    "disposition": {"type": "string"},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "denominator": {
            "type": "object",
            "required": ["generate_now", "update_existing", "deferred_to_backlog", "rejected_with_reason"],
            "properties": {
                "generate_now": {"type": "integer", "minimum": 0},
                "update_existing": {"type": "integer", "minimum": 0},
                "deferred_to_backlog": {"type": "integer", "minimum": 0},
                "rejected_with_reason": {"type": "integer", "minimum": 0},
                "blocked_with_reason": {"type": "integer", "minimum": 0},
            },
        },
    },
}

DENOMINATOR_CHECK_SCHEMA = {
    "type": "object",
    "required": ["valid", "total_candidates", "bucket_sum", "buckets", "delta"],
    "properties": {
        "valid": {"type": "boolean"},
        "total_candidates": {"type": "integer", "minimum": 0},
        "bucket_sum": {"type": "integer", "minimum": 0},
        "buckets": {
            "type": "object",
            "required": ["generate_now", "update_existing", "deferred_to_backlog", "rejected_with_reason", "blocked_with_reason"],
            "properties": {
                "generate_now": {"type": "integer", "minimum": 0},
                "update_existing": {"type": "integer", "minimum": 0},
                "deferred_to_backlog": {"type": "integer", "minimum": 0},
                "rejected_with_reason": {"type": "integer", "minimum": 0},
                "blocked_with_reason": {"type": "integer", "minimum": 0},
            },
        },
        "delta": {"type": "integer"},
    },
}

HANDOFF_MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["family", "platform", "dry_run", "manifest_items"],
    "properties": {
        "family": {"type": "string"},
        "platform": {"type": "string"},
        "dry_run": {"type": "boolean"},
        "manifest_items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["cluster", "subdomain", "action", "target_skill", "score"],
                "properties": {
                    "cluster": {"type": "string"},
                    "subdomain": {"type": "string"},
                    "action": {"type": "string"},
                    "target_skill": {"type": "string"},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}
