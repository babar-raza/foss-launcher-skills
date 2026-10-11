"""session_identity.py — Shared caller-identity resolution (production
concurrency redesign, 2026-08-01; extracted from skill_context.py's
_derive_session_id, RC1/RC2 hardening, 2026-07-31).

Precedence: explicit > ``AGENT_SESSION_ID`` env > ``CODEX_THREAD_ID`` env >
``CLAUDE_CODE_SESSION_ID`` env > ``None``.

``CODEX_THREAD_ID`` is Codex's own per-thread identity, present for every
Codex-driven call — treating it as a stable identity prevents Codex callers
from silently falling back to a shared legacy single-slot state file.

``CLAUDE_CODE_SESSION_ID`` is the harness's own per-conversation identifier —
inherited into every tool-call subprocess automatically, unlike
``AGENT_SESSION_ID``/an explicit id, which the caller must remember to
re-supply on every single call (this harness's Bash tool does not persist
shell state across invocations). It is a LAST-RESORT fallback, not a
replacement for explicit identity: it is shared by a conversation with any
subagents it spawns (verified empirically), so parallel subagents from one
conversation are not distinguished from each other by this tier alone. What
it does fix is the common case this repo actually hit in production: two
genuinely independent, separately-initiated sessions/conversations, which the
harness assigns *different* ``CLAUDE_CODE_SESSION_ID`` values, so a
scope-overlap conflict check correctly compares two distinct identities
instead of both silently falling to a coarser, identity-less path. An earlier
design used session_ledger.py's shared, mutable reports/session-state/ACTIVE
pointer file as this fallback instead; live-tested against a genuinely
concurrent second session, it collided (both processes read the same file and
believed it was their own identity) and was reverted in full.

Every consumer of this module must independently decide whether wiring the
``CLAUDE_CODE_SESSION_ID`` tier into ITS OWN default-identity-generation path
(not just its resolution/lookup path) is safe for its own storage model —
resolving to an id that nothing is ever filed under is a no-op, and wiring
generation to match resolution can introduce new collision classes specific
to that consumer's data shape (see session_ledger.py's own file-touch-ledger
commingling risk, deliberately NOT addressed by this module alone).
"""
from __future__ import annotations

import os

ENV_AGENT_SESSION_ID = "AGENT_SESSION_ID"
ENV_CODEX_THREAD_ID = "CODEX_THREAD_ID"
ENV_CLAUDE_CODE_SESSION_ID = "CLAUDE_CODE_SESSION_ID"


def resolve(explicit: "str | None" = None) -> "str | None":
    """Return the raw resolved identity string (unsanitized), or None.

    Precedence: explicit > AGENT_SESSION_ID > CODEX_THREAD_ID >
    CLAUDE_CODE_SESSION_ID > None.
    """
    return (
        explicit
        or os.environ.get(ENV_AGENT_SESSION_ID, "").strip()
        or os.environ.get(ENV_CODEX_THREAD_ID, "").strip()
        or os.environ.get(ENV_CLAUDE_CODE_SESSION_ID, "").strip()
        or None
    )


def sanitize(value: str, max_len: int = 64) -> str:
    """Sanitize a raw identity string for safe use as a filename component."""
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in value)[:max_len]


def resolve_sanitized(explicit: "str | None" = None, max_len: int = 64) -> "str | None":
    """resolve() + sanitize() — the common case for callers that use the
    resolved identity as a filename component (e.g. reports/skill-context/
    active/{session_id}.json)."""
    value = resolve(explicit)
    return sanitize(value, max_len) if value else None
