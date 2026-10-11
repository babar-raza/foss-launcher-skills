#!/usr/bin/env python3
"""Verify that a replica tree matches its split-manifest (plan decision D4).

verify_split_manifest.py --repo GITDIR --ref REF --manifest-dir DIR
                         [--base-commit SHA] [--aspose-repo GITDIR] [--evidence DIR]
                         [--tree-prefix split-manifest/]

Passes only if all of these hold:
  1. the set of paths in the tree of REF is exactly transferred.tsv paths plus
     additions.tsv paths (no extra file, no missing file);
  2. every count and sha256 in manifest.json matches the TSV files recomputed;
  3. no path is listed twice, or in both transferred and not-transferred, or in
     additions together with either of them; every additions path exists in the tree;
  4. the manifest files in the tree (TREE_PREFIX) are byte-equal to DIR (not stale);
  5. with --base-commit, manifest.json names that base commit.
Optional deeper checks: --aspose-repo recomputes the universe and stays_sha256 from the
base tree of the monorepo (read-only ls-tree); --evidence compares the policy sha256.

Exit 0 pass, 1 fail, 2 tool error. The report names the first 20 offending paths per check.
stays_sha256 and policy_sha256 cannot be recomputed from the manifest files alone; without
the optional flags they are only checked for shape (64 hex).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_FILES = ["MANIFEST.md", "additions.tsv", "manifest.json",
                  "not-transferred.tsv", "stays.rules.tsv", "transferred.tsv"]
HEADERS = {
    "transferred.tsv": ["path", "bucket", "rule"],
    "not-transferred.tsv": ["path", "bucket", "rule", "reason"],
    "stays.rules.tsv": ["bucket", "rule", "files", "top_level"],
    "additions.tsv": ["path", "reason", "source"],
}
LIMIT = 20


class ToolError(Exception):
    """Environment problem: missing file, git failure (exit 2)."""


class Report:
    def __init__(self):
        self.items = []
        self.info = []

    def fail(self, check, message, paths=()):
        self.items.append((check, message, sorted(paths)))

    def ok(self):
        return not self.items

    def text(self):
        out = list(self.info)
        for check, message, paths in self.items:
            out.append(f"FAIL [{check}] {message}")
            for p in paths[:LIMIT]:
                out.append(f"    {p}")
            if len(paths) > LIMIT:
                out.append(f"    ... and {len(paths) - LIMIT} more")
        out.append("RESULT: PASS" if self.ok() else f"RESULT: FAIL ({len(self.items)} failing check(s))")
        return "\n".join(out)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def paths_sha256(paths):
    return sha256_bytes(("\n".join(sorted(paths)) + "\n").encode("utf-8"))


def blob_id(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=off", *args],
                           capture_output=True)
    except OSError as e:
        raise ToolError(f"cannot run git: {e}")
    if r.returncode != 0:
        raise ToolError(f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def tree_entries(repo, ref):
    """{path: (mode, type, oid)} of every entry of the tree of REF."""
    git(repo, "rev-parse", "--verify", ref + "^{commit}")
    raw = git(repo, "ls-tree", "-r", "-z", ref)
    out = {}
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, typ, oid = meta.decode().split(" ")
        out[path.decode("utf-8")] = (mode, typ, oid)
    return out


def read_file(path):
    try:
        return Path(path).read_bytes()
    except OSError as e:
        raise ToolError(f"cannot read {path}: {e}")


def parse_tsv(data, name, rep):
    if b"\r" in data:
        rep.fail("parse", f"{name}: contains CR characters")
        return None
    lines = data.decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    header = HEADERS[name]
    if not lines or lines[0].split("\t") != header:
        rep.fail("parse", f"{name}: header is not {header}")
        return None
    rows, bad = [], []
    for n, line in enumerate(lines[1:], start=2):
        cols = line.split("\t")
        if len(cols) != len(header):
            bad.append(f"{name}:{n}")
        else:
            rows.append(cols)
    if bad:
        rep.fail("parse", f"{name}: rows with the wrong column count", bad)
        return None
    return rows


def dups(paths):
    seen, d = set(), set()
    for p in paths:
        if p in seen:
            d.add(p)
        seen.add(p)
    return d


def by_bucket(rows, idx):
    o = {}
    for r in rows:
        o[r[idx]] = o.get(r[idx], 0) + 1
    return dict(sorted(o.items()))


def check_counts_and_hashes(mj, tr, nt, st, ad, raw, rep):
    for key in ("schema_version", "base", "counts", "buckets", "hashes", "files"):
        if key not in mj:
            rep.fail("manifest.json", f"missing key {key!r}")
            return False
    c, h, f = mj["counts"], mj["hashes"], mj["files"]
    if not (isinstance(mj["base"], dict) and HEX40.match(str(mj["base"].get("commit", "")))
            and HEX40.match(str(mj["base"].get("tree", "")))):
        rep.fail("manifest.json", "base.commit / base.tree missing or not 40-hex")
        return False
    if not all(isinstance(x, dict) for x in (c, h, f, mj["buckets"])):
        rep.fail("manifest.json", "counts, hashes, files and buckets must be objects")
        return False
    stays = 0
    for r in st:
        if not r[2].isdigit():
            rep.fail("counts", "stays.rules.tsv: non-numeric files column", [r[1]])
            return False
        stays += int(r[2])
    exp = {"moved": len(tr), "excluded": len(nt), "stays": stays, "additions": len(ad),
           "universe": len(tr) + len(nt) + stays, "replica_files": len(tr) + len(ad)}
    bad = [f"{k}: manifest.json {c.get(k)!r}, recomputed {v!r}" for k, v in exp.items() if c.get(k) != v]
    if bad:
        rep.fail("counts", "counts in manifest.json do not match the TSV files", bad)
    b = mj["buckets"]
    for k, v in (("moved", by_bucket(tr, 1)), ("excluded", by_bucket(nt, 1)), ("stays", {"R": stays})):
        if b.get(k) != v:
            rep.fail("counts", f"bucket counts {k!r}: manifest.json {b.get(k)!r}, recomputed {v!r}")
    hbad = []
    for key, val in (("moveset_sha256", paths_sha256([r[0] for r in tr])),
                     ("excluded_sha256", paths_sha256([r[0] for r in nt]))):
        if h.get(key) != val:
            hbad.append(f"{key}: manifest.json {h.get(key)!r}, recomputed {val}")
    for name in ("transferred.tsv", "not-transferred.tsv", "stays.rules.tsv", "additions.tsv"):
        val = sha256_bytes(raw[name])
        if f.get(name) != val:
            hbad.append(f"files[{name}]: manifest.json {f.get(name)!r}, recomputed {val}")
    for key in ("stays_sha256", "policy_sha256"):
        if not HEX64.match(str(h.get(key, ""))):
            hbad.append(f"{key}: not a 64-hex value")
    if hbad:
        rep.fail("hashes", "sha256 values in manifest.json do not match", hbad)
    return True


def check_disjoint(tr, nt, ad, rep):
    tp, np_, ap = [r[0] for r in tr], [r[0] for r in nt], [r[0] for r in ad]
    for label, lst in (("transferred", tp), ("not-transferred", np_), ("additions", ap)):
        d = dups(lst)
        if d:
            rep.fail("duplicates", f"{len(d)} path(s) listed twice in {label}", d)
    for la, a, lb, b in (("transferred", tp, "not-transferred", np_),
                         ("additions", ap, "transferred", tp),
                         ("additions", ap, "not-transferred", np_)):
        both = set(a) & set(b)
        if both:
            rep.fail("overlap", f"{len(both)} path(s) in both {la} and {lb}", both)


def check_tree(entries, tp, ap, rep):
    expected = set(tp) | set(ap)
    have = set(entries)
    extra, missing = have - expected, expected - have
    if extra:
        rep.fail("tree", f"{len(extra)} path(s) in the tree are in neither transferred.tsv nor additions.tsv", extra)
    miss_t = missing & set(tp)
    miss_a = missing & set(ap)
    if miss_t:
        rep.fail("tree", f"{len(miss_t)} path(s) listed as transferred are absent from the tree", miss_t)
    if miss_a:
        rep.fail("tree", f"{len(miss_a)} path(s) listed in additions.tsv do not exist in the tree", miss_a)


def check_stale(entries, mdir, prefix, rep):
    stale = []
    for name in MANIFEST_FILES:
        e = entries.get(prefix + name)
        p = Path(mdir) / name
        if e is None or not p.exists():
            continue
        if e[2] != blob_id(p.read_bytes()):
            stale.append(prefix + name)
    if stale:
        rep.fail("stale", "manifest file(s) in the tree differ from the manifest directory", stale)


def check_aspose(mj, tp, np_, aspose_repo, rep):
    base = mj["base"]["commit"]
    tree = git(aspose_repo, "rev-parse", base + "^{tree}").decode().strip()
    if tree != mj["base"]["tree"]:
        rep.fail("aspose", f"base tree: manifest.json {mj['base']['tree']}, repository {tree}")
    raw = git(aspose_repo, "ls-tree", "-r", "-z", "--name-only", base)
    universe = {p.decode("utf-8") for p in raw.split(b"\0") if p}
    if len(universe) != mj["counts"]["universe"]:
        rep.fail("aspose", f"universe: manifest.json {mj['counts']['universe']}, base tree {len(universe)}")
    stray = (set(tp) | set(np_)) - universe
    if stray:
        rep.fail("aspose", f"{len(stray)} listed path(s) are not in the base tree", stray)
    stays = universe - set(tp) - set(np_)
    if len(stays) != mj["counts"]["stays"]:
        rep.fail("aspose", f"stays: manifest.json {mj['counts']['stays']}, recomputed {len(stays)}")
    val = paths_sha256(stays)
    if val != mj["hashes"]["stays_sha256"]:
        rep.fail("aspose", f"stays_sha256: manifest.json {mj['hashes']['stays_sha256']}, recomputed {val}")


def check_policy(mj, evidence, rep):
    m = re.search(r"policy:\s*`[^`]*`\s*sha256\s*`([0-9a-f]{64})`",
                  read_file(Path(evidence) / "report.md").decode("utf-8"))
    if not m or m.group(1) != mj["hashes"]["policy_sha256"]:
        rep.fail("policy", f"policy_sha256 differs from {evidence}/report.md ({m.group(1) if m else 'not found'})")


def verify(repo, ref, manifest_dir, base_commit=None, aspose_repo=None, evidence=None,
           tree_prefix="split-manifest/"):
    rep = Report()
    mdir = Path(manifest_dir)
    raw = {n: read_file(mdir / n) for n in
           ("manifest.json", "transferred.tsv", "not-transferred.tsv", "stays.rules.tsv", "additions.tsv")}
    try:
        mj = json.loads(raw["manifest.json"].decode("utf-8"))
    except ValueError as e:
        rep.fail("manifest.json", f"not valid JSON: {e}")
        return rep
    tabs = {n: parse_tsv(raw[n], n, rep) for n in HEADERS}
    entries = tree_entries(repo, ref)
    if any(v is None for v in tabs.values()):
        return rep
    tr, nt, st, ad = (tabs["transferred.tsv"], tabs["not-transferred.tsv"],
                      tabs["stays.rules.tsv"], tabs["additions.tsv"])
    if check_counts_and_hashes(mj, tr, nt, st, ad, raw, rep):
        check_disjoint(tr, nt, ad, rep)
        check_tree(entries, [r[0] for r in tr], [r[0] for r in ad], rep)
        rep.info.append(f"checked: tree {len(entries)} paths; transferred {len(tr)}, additions {len(ad)}, "
                        f"not-transferred {len(nt)}, stays {mj['counts']['stays']}")
        check_stale(entries, mdir, tree_prefix, rep)
        if base_commit is not None:
            if not HEX40.match(base_commit):
                raise ToolError("--base-commit must be a full 40-hex id")
            if mj["base"].get("commit") != base_commit:
                rep.fail("base", f"manifest.json base {mj['base'].get('commit')!r}, expected {base_commit}")
        if aspose_repo:
            check_aspose(mj, [r[0] for r in tr], [r[0] for r in nt], aspose_repo, rep)
            rep.info.append("checked: universe and stays_sha256 recomputed from the base tree")
        if evidence:
            check_policy(mj, evidence, rep)
            rep.info.append("checked: policy_sha256 equals evidence report.md")
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", required=True, help="git directory holding the replica")
    ap.add_argument("--ref", required=True, help="commit-ish whose tree is checked")
    ap.add_argument("--manifest-dir", required=True, help="directory with manifest.json and the TSV files")
    ap.add_argument("--base-commit", help="expected aspose.org base commit (40-hex)")
    ap.add_argument("--aspose-repo", help="aspose.org git directory: recompute universe and stays_sha256")
    ap.add_argument("--evidence", help="S1 evidence directory: compare policy_sha256 with report.md")
    ap.add_argument("--tree-prefix", default="split-manifest/", help="where the manifest lives in the tree")
    a = ap.parse_args(argv)
    try:
        rep = verify(a.repo, a.ref, a.manifest_dir, a.base_commit, a.aspose_repo, a.evidence, a.tree_prefix)
    except ToolError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(rep.text())
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
