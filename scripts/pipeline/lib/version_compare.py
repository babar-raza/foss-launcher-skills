"""Per-registry monotonic version comparators (MT075-T1, plan Revision 2 §R2.5).

Every registry type the site supports orders versions differently, and the
registry's own schema (`package_registry_data.py`) has never had a
version-ordering check at all -- `candidate.version` is untyped
`string|None`. This module is the one place "is B actually newer than A, in
THIS registry's own scheme" gets decided, so every auto-apply decision
(Tier 1/2 in `check_registry_merge_safety.py`, `registry_watch.py`) calls
into exactly one of these functions rather than re-deriving comparison
logic ad hoc per call site -- the inconsistency named in the governing
plan's §R2.3 (point 2).

Scope and honesty note (do not overclaim): `compare_maven` implements the
common-case subset of Maven's real `ComparableVersion` algorithm --
numeric dotted components plus a single well-known qualifier suffix
(alpha/beta/milestone/rc/snapshot/ga/sp). It is not a full reimplementation
of Maven's arbitrary mixed digit/alpha-run tokenizer, which handles far
stranger inputs than any real Aspose FOSS coordinate has ever used. If a
version string doesn't fit the supported shapes, parsing raises
`VersionParseError` rather than silently guessing an order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from packaging.version import InvalidVersion
from packaging.version import Version as _PyPIVersion

REGISTRY_TYPES = ("pypi", "nuget", "npm", "go_modules", "cargo", "maven")


class VersionParseError(ValueError):
    """A version string could not be parsed under the given registry's scheme."""


# ---------------------------------------------------------------------------
# Shared semver-core machinery (npm, cargo, go_modules all use it)
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True)
class _SemverCore:
    major: int
    minor: int
    patch: int
    prerelease: tuple  # tuple of str|int identifiers; empty == release


def _parse_semver_core(raw: str) -> _SemverCore:
    m = _SEMVER_RE.match(raw)
    if not m:
        raise VersionParseError(f"not a valid semver core string: {raw!r}")
    pre_raw = m.group("prerelease")
    if not pre_raw:
        pre: tuple = ()
    else:
        parts = []
        for ident in pre_raw.split("."):
            parts.append(int(ident) if ident.isdigit() else ident)
        pre = tuple(parts)
    return _SemverCore(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        prerelease=pre,
    )


def _compare_semver_identifier(a, b) -> int:
    a_is_num = isinstance(a, int)
    b_is_num = isinstance(b, int)
    if a_is_num and b_is_num:
        return (a > b) - (a < b)
    if a_is_num != b_is_num:
        # semver.org spec, precedence rule 4: numeric identifiers always
        # have LOWER precedence than alphanumeric ones in the same position.
        return -1 if a_is_num else 1
    return (a > b) - (a < b)  # both alphanumeric: ASCII lexical


def _compare_semver_core(a: _SemverCore, b: _SemverCore) -> int:
    for x, y in ((a.major, b.major), (a.minor, b.minor), (a.patch, b.patch)):
        if x != y:
            return -1 if x < y else 1
    # A version with no prerelease outranks one that has any prerelease.
    if not a.prerelease and not b.prerelease:
        return 0
    if not a.prerelease:
        return 1
    if not b.prerelease:
        return -1
    for x, y in zip(a.prerelease, b.prerelease):
        c = _compare_semver_identifier(x, y)
        if c != 0:
            return c
    # Equal so far: the longer prerelease identifier list has higher precedence.
    return (len(a.prerelease) > len(b.prerelease)) - (len(a.prerelease) < len(b.prerelease))


def _is_semver_prerelease(raw: str) -> bool:
    return bool(_parse_semver_core(raw).prerelease)


# ---------------------------------------------------------------------------
# pypi (PEP 440)
# ---------------------------------------------------------------------------

def compare_pypi(a: str, b: str) -> int:
    try:
        va, vb = _PyPIVersion(a), _PyPIVersion(b)
    except InvalidVersion as exc:
        raise VersionParseError(str(exc)) from exc
    return (va > vb) - (va < vb)


def is_prerelease_pypi(version: str) -> bool:
    try:
        return _PyPIVersion(version).is_prerelease
    except InvalidVersion as exc:
        raise VersionParseError(str(exc)) from exc


# ---------------------------------------------------------------------------
# nuget (SemVer2 + legacy 4-part System.Version numeric component)
# ---------------------------------------------------------------------------

_NUGET_RE = re.compile(
    r"^(?P<nums>\d+(?:\.\d+){0,3})"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True)
class _NuGetVersion:
    nums: tuple  # always length 4, missing trailing parts default to 0
    prerelease: tuple


def _parse_nuget(raw: str) -> _NuGetVersion:
    m = _NUGET_RE.match(raw)
    if not m:
        raise VersionParseError(f"not a valid NuGet version string: {raw!r}")
    nums = [int(p) for p in m.group("nums").split(".")]
    nums += [0] * (4 - len(nums))
    pre_raw = m.group("prerelease")
    if not pre_raw:
        pre: tuple = ()
    else:
        # NuGet compares prerelease labels case-INsensitively (unlike strict
        # semver.org, which the shared _compare_semver_core/_parse_semver_core
        # machinery below correctly keeps case-sensitive for npm/cargo/go).
        # Independent review (2026-09-28) reproduced "1.0.0-Beta" sorting
        # below "1.0.0-alpha" without this normalization.
        pre = tuple(int(p) if p.isdigit() else p.lower() for p in pre_raw.split("."))
    return _NuGetVersion(nums=tuple(nums), prerelease=pre)


def compare_nuget(a: str, b: str) -> int:
    va, vb = _parse_nuget(a), _parse_nuget(b)
    for x, y in zip(va.nums, vb.nums):
        if x != y:
            return -1 if x < y else 1
    if not va.prerelease and not vb.prerelease:
        return 0
    if not va.prerelease:
        return 1
    if not vb.prerelease:
        return -1
    for x, y in zip(va.prerelease, vb.prerelease):
        c = _compare_semver_identifier(x, y)
        if c != 0:
            return c
    return (len(va.prerelease) > len(vb.prerelease)) - (len(va.prerelease) < len(vb.prerelease))


def is_prerelease_nuget(version: str) -> bool:
    return bool(_parse_nuget(version).prerelease)


# ---------------------------------------------------------------------------
# npm / cargo (strict SemVer 2.0.0 core)
# ---------------------------------------------------------------------------

def compare_npm(a: str, b: str) -> int:
    return _compare_semver_core(_parse_semver_core(a), _parse_semver_core(b))


def compare_cargo(a: str, b: str) -> int:
    return _compare_semver_core(_parse_semver_core(a), _parse_semver_core(b))


def is_prerelease_npm(version: str) -> bool:
    return _is_semver_prerelease(version)


def is_prerelease_cargo(version: str) -> bool:
    return _is_semver_prerelease(version)


# ---------------------------------------------------------------------------
# go_modules (SemVer core, mandatory 'v' prefix per proxy.golang.org convention)
# ---------------------------------------------------------------------------

def compare_go(a: str, b: str) -> int:
    return _compare_semver_core(_parse_go_core(a), _parse_go_core(b))


def _parse_go_core(raw: str) -> _SemverCore:
    if not raw.startswith("v"):
        raise VersionParseError(
            f"go module version must start with 'v' (proxy.golang.org convention): {raw!r}"
        )
    return _parse_semver_core(raw[1:])


def is_prerelease_go(version: str) -> bool:
    return bool(_parse_go_core(version).prerelease)


# ---------------------------------------------------------------------------
# maven (common-case subset of ComparableVersion -- see module docstring)
# ---------------------------------------------------------------------------

# Maven's real qualifier precedence table (ComparableVersion.QUALIFIERS),
# with "" standing for "no qualifier" (a release) and ga/final treated as
# aliases for "" per Maven's own alias table. "cr" and "rc" share a rank --
# Maven's real ComparableVersion treats them as equivalent aliases, not a
# strict rc<cr ordering (independent review, 2026-09-28, reproduced
# "1.0-cr1" outranking "1.0-rc2" under the old strict-tuple-index version).
_MAVEN_QUALIFIER_RANK = {
    "alpha": 0, "beta": 1, "milestone": 2, "rc": 3, "cr": 3, "snapshot": 4, "": 5, "sp": 6,
}
_MAVEN_QUALIFIER_ORDER = tuple(_MAVEN_QUALIFIER_RANK)
_MAVEN_RELEASE_RANK = _MAVEN_QUALIFIER_RANK[""]
_MAVEN_QUALIFIER_ALIASES = {"ga": "", "final": "", "release": ""}

_MAVEN_RE = re.compile(r"^(?P<nums>\d+(?:\.\d+)*)(?:-(?P<qualifier>[0-9A-Za-z]+))?$")


@dataclass(frozen=True)
class _MavenVersion:
    nums: tuple
    qualifier_rank: int
    qualifier_number: Optional[int]  # e.g. "rc1" / "rc-1" -> 1, for same-qualifier ordering


def _parse_maven(raw: str) -> _MavenVersion:
    m = _MAVEN_RE.match(raw)
    if not m:
        raise VersionParseError(
            f"not a supported Maven version shape (numeric dots + one optional "
            f"qualifier suffix): {raw!r}"
        )
    nums = tuple(int(p) for p in m.group("nums").split("."))
    qualifier_raw = (m.group("qualifier") or "").lower()
    qualifier_number = None
    if qualifier_raw:
        trail = re.match(r"^([a-z]+)(\d+)?$", qualifier_raw)
        if trail:
            word, num = trail.group(1), trail.group(2)
            qualifier_raw = word
            qualifier_number = int(num) if num is not None else None
    qualifier_raw = _MAVEN_QUALIFIER_ALIASES.get(qualifier_raw, qualifier_raw)
    if qualifier_raw not in _MAVEN_QUALIFIER_ORDER:
        raise VersionParseError(
            f"unrecognized Maven qualifier {qualifier_raw!r} in {raw!r}; supported: "
            f"{_MAVEN_QUALIFIER_ORDER}"
        )
    return _MavenVersion(
        nums=nums,
        qualifier_rank=_MAVEN_QUALIFIER_RANK[qualifier_raw],
        qualifier_number=qualifier_number,
    )


def compare_maven(a: str, b: str) -> int:
    va, vb = _parse_maven(a), _parse_maven(b)
    na, nb = va.nums, vb.nums
    length = max(len(na), len(nb))
    na = na + (0,) * (length - len(na))
    nb = nb + (0,) * (length - len(nb))
    for x, y in zip(na, nb):
        if x != y:
            return -1 if x < y else 1
    if va.qualifier_rank != vb.qualifier_rank:
        return -1 if va.qualifier_rank < vb.qualifier_rank else 1
    qa = va.qualifier_number if va.qualifier_number is not None else 0
    qb = vb.qualifier_number if vb.qualifier_number is not None else 0
    return (qa > qb) - (qa < qb)


def is_prerelease_maven(version: str) -> bool:
    v = _parse_maven(version)
    release_rank = _MAVEN_RELEASE_RANK
    return v.qualifier_rank < release_rank


# ---------------------------------------------------------------------------
# Unified dispatch
# ---------------------------------------------------------------------------

_COMPARE_FUNCS = {
    "pypi": compare_pypi,
    "nuget": compare_nuget,
    "npm": compare_npm,
    "go_modules": compare_go,
    "cargo": compare_cargo,
    "maven": compare_maven,
}

_PRERELEASE_FUNCS = {
    "pypi": is_prerelease_pypi,
    "nuget": is_prerelease_nuget,
    "npm": is_prerelease_npm,
    "go_modules": is_prerelease_go,
    "cargo": is_prerelease_cargo,
    "maven": is_prerelease_maven,
}


def compare(registry_type: str, a: str, b: str) -> int:
    """Return -1/0/1 for a<b / a==b / a>b, ordered per `registry_type`'s own scheme.

    Raises VersionParseError (never a bare exception) if either string does
    not parse under that registry's scheme, and KeyError if registry_type is
    not one of REGISTRY_TYPES -- callers should always validate registry_type
    against the schema enum first (package_registry_data.py already does).
    """
    func = _COMPARE_FUNCS[registry_type]
    return func(a, b)


def is_newer(registry_type: str, current: Optional[str], candidate: str) -> bool:
    """True iff `candidate` is strictly newer than `current` under this registry's
    ordering. A missing/None `current` (no confirmed version yet) always counts
    the candidate as newer -- there is nothing to be "newer than" yet."""
    if not current:
        return True
    return compare(registry_type, candidate, current) > 0


def is_prerelease(registry_type: str, version: str) -> bool:
    return _PRERELEASE_FUNCS[registry_type](version)
