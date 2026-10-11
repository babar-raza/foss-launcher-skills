"""Tests for build_split_manifest.py and verify_split_manifest.py.

Temporary git repositories only: no network, no access to aspose.org. The negative
controls (a failing verifier is the expected result) are named test_neg_*.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_split_manifest as bsm  # noqa: E402
import verify_split_manifest as vsm  # noqa: E402

VERIFY = HERE / "verify_split_manifest.py"
BUILD = HERE / "build_split_manifest.py"
BASE = "7b6ee715fb95c112d162804e3d8c6a8e10eb5128"
BASE_TREE = "791c4e132ac6f30bf0f2b70c8d33f2b1a31acd3b"
POLICY = "4a99635505f18f9b9421fbc74bc5dd16a6f0755f414691f1eb7334d45fc3549e"
STAYS_SHA = "a" * 64

TRANSFERRED = [("scripts/a.py", "M", "R3-x"), ("skills/x/SKILL.md", "M", "R4-skills"),
               ("docs/old.md", "A", "R9-docs-archive"), (".claude/s.md", "S", "S-claude")]
NOT_TRANSFERRED = [(".github/workflows/w1.yml", "A", "R9-github-workflows", "ci"),
                   (".github/workflows/w2.yml", "A", "R9-github-workflows", "ci")]
STAYS = [("R", "R2-content-sites", "7", "content"), ("R", "R2-themes", "3", "themes")]
ADDITIONS = [("README.md", "new readme", "new"), (".gitignore", "policy", "copy")]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def tsv(header, rows):
    return ("\t".join(header) + "\n" + "".join("\t".join(r) + "\n" for r in rows)).encode()


def write_evidence(d, transferred=TRANSFERRED, nt=NOT_TRANSFERRED, stays=STAYS, stays_sha=STAYS_SHA):
    d.mkdir(parents=True, exist_ok=True)
    (d / "transferred.tsv").write_bytes(tsv(vsm.HEADERS["transferred.tsv"], transferred))
    (d / "not-transferred.tsv").write_bytes(tsv(vsm.HEADERS["not-transferred.tsv"], nt))
    (d / "stays.rules.tsv").write_bytes(tsv(vsm.HEADERS["stays.rules.tsv"], stays))
    n_stays = sum(int(r[2]) for r in stays)
    hashes = {"base": BASE, "base_tree": BASE_TREE, "moved": len(transferred), "excluded": len(nt),
              "stays": n_stays, "universe": len(transferred) + len(nt) + n_stays,
              "moveset_sha256": vsm.paths_sha256([r[0] for r in transferred]),
              "excluded_sha256": vsm.paths_sha256([r[0] for r in nt]), "stays_sha256": stays_sha}
    (d / "hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
    (d / "report.md").write_text(f"- policy: `split-policy` sha256 `{POLICY}`\n", encoding="utf-8")


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "core.autocrlf=false", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)


def refresh_manifest(mdir):
    """Recompute manifest.json counts and hashes after a test edited the TSV files."""
    def rows(name):
        return vsm.parse_tsv((mdir / name).read_bytes(), name, vsm.Report())
    tr, nt, st, ad = (rows("transferred.tsv"), rows("not-transferred.tsv"),
                      rows("stays.rules.tsv"), rows("additions.tsv"))
    mj = json.loads((mdir / "manifest.json").read_text(encoding="utf-8"))
    stays = sum(int(r[2]) for r in st)
    mj["counts"].update(moved=len(tr), excluded=len(nt), stays=stays, additions=len(ad),
                        universe=len(tr) + len(nt) + stays, replica_files=len(tr) + len(ad))
    mj["buckets"] = {"moved": vsm.by_bucket(tr, 1), "excluded": vsm.by_bucket(nt, 1), "stays": {"R": stays}}
    mj["hashes"]["moveset_sha256"] = vsm.paths_sha256([r[0] for r in tr])
    mj["hashes"]["excluded_sha256"] = vsm.paths_sha256([r[0] for r in nt])
    for n in ("transferred.tsv", "not-transferred.tsv", "stays.rules.tsv", "additions.tsv"):
        mj["files"][n] = sha((mdir / n).read_bytes())
    (mdir / "manifest.json").write_bytes((json.dumps(mj, indent=1, sort_keys=True) + "\n").encode())


class World:
    """Evidence + built manifest directory + a git repo whose tree is meant to match."""

    def __init__(self, tmp, additions=ADDITIONS, mutate=None, drop=(), extra=(), **evidence):
        self.tmp = tmp
        self.ev = tmp / "ev"
        write_evidence(self.ev, **evidence)
        seed = tmp / "seed.tsv"
        seed.write_bytes(tsv(vsm.HEADERS["additions.tsv"], additions))
        self.mdir = tmp / "out" / "split-manifest"
        self.mj = bsm.build(self.ev, seed, self.mdir, date="2026-10-11")
        if mutate:
            mutate(self.mdir)
        self.repo = tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        paths = [r[0] for r in TRANSFERRED] + [r[0] for r in additions] + list(extra)
        for p in paths:
            if p in drop:
                continue
            f = self.repo / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"content of {p}\n", encoding="utf-8")
        for n in vsm.MANIFEST_FILES:
            (self.repo / "split-manifest").mkdir(exist_ok=True)
            (self.repo / "split-manifest" / n).write_bytes((self.mdir / n).read_bytes())
        git(self.repo, "add", "-f", "-A")
        git(self.repo, "commit", "-q", "-m", "tree")

    def verify(self, *extra):
        return run(VERIFY, "--repo", self.repo, "--ref", "HEAD", "--manifest-dir", self.mdir, *extra)


def edit_json(path, fn):
    mj = json.loads(path.read_text(encoding="utf-8"))
    fn(mj)
    path.write_bytes((json.dumps(mj, indent=1, sort_keys=True) + "\n").encode())


# ---- builder -------------------------------------------------------------

def test_build_is_deterministic_and_idempotent(tmp_path):
    a = World(tmp_path / "a")
    b = World(tmp_path / "b")
    for n in vsm.MANIFEST_FILES:
        assert (a.mdir / n).read_bytes() == (b.mdir / n).read_bytes(), n
    before = {n: (a.mdir / n).read_bytes() for n in vsm.MANIFEST_FILES}
    bsm.build(a.ev, a.mdir / "additions.tsv", a.mdir)  # feed its own output, no date needed
    assert {n: (a.mdir / n).read_bytes() for n in vsm.MANIFEST_FILES} == before
    assert b"2026" not in (a.mdir / "manifest.json").read_bytes()  # no timestamps in data files


def test_build_lists_manifest_files_in_additions_and_counts(tmp_path):
    w = World(tmp_path)
    rows = vsm.parse_tsv((w.mdir / "additions.tsv").read_bytes(), "additions.tsv", vsm.Report())
    paths = [r[0] for r in rows]
    assert paths == sorted(paths)
    assert {"split-manifest/" + n for n in vsm.MANIFEST_FILES} <= set(paths)
    assert w.mj["counts"]["additions"] == len(ADDITIONS) + 6
    assert w.mj["counts"]["replica_files"] == len(TRANSFERRED) + len(ADDITIONS) + 6
    assert w.mj["counts"]["universe"] == 4 + 2 + 10
    assert w.mj["hashes"]["policy_sha256"] == POLICY


def test_change_log_kept_and_extended(tmp_path):
    w = World(tmp_path)
    bsm.build(w.ev, w.mdir / "additions.tsv", w.mdir, date="2026-11-01", log_entry="refresh at new base")
    md = (w.mdir / "MANIFEST.md").read_text(encoding="utf-8")
    assert "- 2026-10-11: Created." in md and "- 2026-11-01: refresh at new base" in md


def test_build_refuses_overlap_and_stale_hashes(tmp_path):
    ev = tmp_path / "ev"
    write_evidence(ev, nt=NOT_TRANSFERRED + [("scripts/a.py", "A", "R9-x", "dup")])
    seed = tmp_path / "s.tsv"
    seed.write_bytes(tsv(vsm.HEADERS["additions.tsv"], ADDITIONS))
    with pytest.raises(bsm.ManifestError, match="both transferred and not-transferred"):
        bsm.build(ev, seed, tmp_path / "o1", date="2026-10-11")
    write_evidence(ev)
    h = json.loads((ev / "hashes.json").read_text())
    h["moved"] = 99
    (ev / "hashes.json").write_text(json.dumps(h))
    with pytest.raises(bsm.ManifestError, match="moved"):
        bsm.build(ev, seed, tmp_path / "o2", date="2026-10-11")
    assert not (tmp_path / "o2").exists()


def test_build_refuses_addition_overlapping_transferred_and_missing_date(tmp_path):
    ev = tmp_path / "ev"
    write_evidence(ev)
    seed = tmp_path / "s.tsv"
    seed.write_bytes(tsv(vsm.HEADERS["additions.tsv"], ADDITIONS + [("scripts/a.py", "r", "s")]))
    with pytest.raises(bsm.ManifestError, match="both additions and transferred"):
        bsm.build(ev, seed, tmp_path / "o", date="2026-10-11")
    seed.write_bytes(tsv(vsm.HEADERS["additions.tsv"], ADDITIONS))
    with pytest.raises(bsm.ManifestError, match="--date"):
        bsm.build(ev, seed, tmp_path / "o")


def test_build_cli_exit_codes(tmp_path):
    w = World(tmp_path)
    ok = run(BUILD, "--evidence", w.ev, "--additions", w.mdir / "additions.tsv", "--out", w.mdir)
    assert ok.returncode == 0, ok.stderr
    bad = run(BUILD, "--evidence", tmp_path / "nope", "--additions", w.mdir / "additions.tsv", "--out", tmp_path / "x")
    assert bad.returncode == 2


# ---- verifier: positive --------------------------------------------------

def test_pass_on_consistent_tree(tmp_path):
    w = World(tmp_path)
    r = w.verify("--base-commit", BASE, "--evidence", w.ev)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULT: PASS" in r.stdout


def test_pass_with_aspose_repo_recompute(tmp_path):
    aspose = tmp_path / "aspose"
    aspose.mkdir()
    git(aspose, "init", "-q")
    universe = [r[0] for r in TRANSFERRED] + [r[0] for r in NOT_TRANSFERRED] + [f"site/p{i}.md" for i in range(10)]
    for p in universe:
        (aspose / p).parent.mkdir(parents=True, exist_ok=True)
        (aspose / p).write_text(p, encoding="utf-8")
    git(aspose, "add", "-f", "-A")
    git(aspose, "commit", "-q", "-m", "base")
    base = git(aspose, "rev-parse", "HEAD").strip()
    tree = git(aspose, "rev-parse", "HEAD^{tree}").strip()
    stays = vsm.paths_sha256([p for p in universe if p.startswith("site/")])
    ev = tmp_path / "w" / "ev"
    write_evidence(ev, stays=[("R", "R2-site", "10", "site")], stays_sha=stays)
    h = json.loads((ev / "hashes.json").read_text())
    h.update(base=base, base_tree=tree)
    (ev / "hashes.json").write_text(json.dumps(h))
    seed = tmp_path / "w" / "seed.tsv"
    seed.write_bytes(tsv(vsm.HEADERS["additions.tsv"], ADDITIONS))
    mdir = tmp_path / "w" / "split-manifest"
    bsm.build(ev, seed, mdir, date="2026-10-11")
    repo = tmp_path / "w" / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    for p in [r[0] for r in TRANSFERRED] + [r[0] for r in ADDITIONS]:
        (repo / p).parent.mkdir(parents=True, exist_ok=True)
        (repo / p).write_text(p, encoding="utf-8")
    (repo / "split-manifest").mkdir()
    for n in vsm.MANIFEST_FILES:
        (repo / "split-manifest" / n).write_bytes((mdir / n).read_bytes())
    git(repo, "add", "-f", "-A")
    git(repo, "commit", "-q", "-m", "t")
    args = ["--repo", repo, "--ref", "HEAD", "--manifest-dir", mdir, "--aspose-repo", aspose]
    ok = run(VERIFY, *args)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "stays_sha256 recomputed" in ok.stdout
    edit_json(mdir / "manifest.json", lambda m: m["hashes"].update(stays_sha256="b" * 64))
    bad = run(VERIFY, *args)
    assert bad.returncode == 1 and "stays_sha256" in bad.stdout


# ---- verifier: negative controls (each must fail with exit 1) -----------

def test_neg_file_in_tree_in_neither_list(tmp_path):
    w = World(tmp_path, extra=["stray/unlisted.txt"])
    r = w.verify()
    assert r.returncode == 1
    assert "neither transferred.tsv nor additions.tsv" in r.stdout and "stray/unlisted.txt" in r.stdout


def test_neg_transferred_path_absent_from_tree(tmp_path):
    w = World(tmp_path, drop=["scripts/a.py"])
    r = w.verify()
    assert r.returncode == 1
    assert "absent from the tree" in r.stdout and "scripts/a.py" in r.stdout


def test_neg_changed_hash_in_manifest_json(tmp_path):
    w = World(tmp_path, mutate=lambda d: edit_json(d / "manifest.json",
              lambda m: m["hashes"].update(moveset_sha256="0" * 64)))
    r = w.verify()
    assert r.returncode == 1
    assert "[hashes]" in r.stdout and "moveset_sha256" in r.stdout
    assert "[tree]" not in r.stdout  # only the hash is wrong


def test_neg_changed_count_in_manifest_json(tmp_path):
    w = World(tmp_path, mutate=lambda d: edit_json(d / "manifest.json", lambda m: m["counts"].update(moved=7071)))
    r = w.verify()
    assert r.returncode == 1 and "[counts]" in r.stdout and "moved" in r.stdout


def test_neg_path_in_both_transferred_and_not_transferred(tmp_path):
    def mutate(d):
        nt = d / "not-transferred.tsv"
        nt.write_bytes(nt.read_bytes() + b"scripts/a.py\tA\tR9-x\tdoubled\n")
        refresh_manifest(d)
    w = World(tmp_path, mutate=mutate)
    r = w.verify()
    assert r.returncode == 1
    assert "[overlap]" in r.stdout and "scripts/a.py" in r.stdout
    assert "[counts]" not in r.stdout and "[hashes]" not in r.stdout and "[tree]" not in r.stdout


def test_neg_additions_entry_does_not_exist(tmp_path):
    w = World(tmp_path, additions=ADDITIONS + [("ghost.txt", "r", "s")], drop=["ghost.txt"])
    r = w.verify()
    assert r.returncode == 1
    assert "do not exist in the tree" in r.stdout and "ghost.txt" in r.stdout


def test_neg_tsv_edited_without_regenerating_manifest(tmp_path):
    w = World(tmp_path)
    nt = w.mdir / "not-transferred.tsv"
    nt.write_bytes(nt.read_bytes() + b".github/workflows/w3.yml\tA\tR9-x\tnew\n")
    r = w.verify()
    assert r.returncode == 1
    assert "[counts]" in r.stdout and "[hashes]" in r.stdout and "not-transferred.tsv" in r.stdout


def test_neg_manifest_in_tree_is_stale(tmp_path):
    w = World(tmp_path)
    (w.mdir / "MANIFEST.md").write_bytes((w.mdir / "MANIFEST.md").read_bytes() + b"edited\n")
    r = w.verify()
    assert r.returncode == 1
    assert "[stale]" in r.stdout and "split-manifest/MANIFEST.md" in r.stdout


def test_neg_wrong_base_commit(tmp_path):
    w = World(tmp_path)
    r = w.verify("--base-commit", "1" * 40)
    assert r.returncode == 1 and "[base]" in r.stdout


def test_neg_duplicate_listing(tmp_path):
    def mutate(d):
        tr = d / "transferred.tsv"
        tr.write_bytes(tr.read_bytes() + b"scripts/a.py\tM\tR3-x\n")
        refresh_manifest(d)
    w = World(tmp_path, mutate=mutate)
    r = w.verify()
    assert r.returncode == 1 and "[duplicates]" in r.stdout and "scripts/a.py" in r.stdout


def test_neg_policy_hash_differs_from_evidence(tmp_path):
    w = World(tmp_path)
    (w.ev / "report.md").write_text("- policy: `split-policy` sha256 `" + "c" * 64 + "`\n", encoding="utf-8")
    r = w.verify("--evidence", w.ev)
    assert r.returncode == 1 and "[policy]" in r.stdout


def test_report_names_only_first_20_paths(tmp_path):
    w = World(tmp_path, extra=[f"stray/f{i:02d}.txt" for i in range(25)])
    r = w.verify()
    assert r.returncode == 1
    assert r.stdout.count("stray/f") == 20 and "and 5 more" in r.stdout


def test_exit_2_on_tool_errors(tmp_path):
    w = World(tmp_path)
    assert run(VERIFY, "--repo", w.repo, "--ref", "no-such-ref", "--manifest-dir", w.mdir).returncode == 2
    assert run(VERIFY, "--repo", w.repo, "--ref", "HEAD", "--manifest-dir", tmp_path / "missing").returncode == 2
    assert run(VERIFY, "--repo", tmp_path / "not-a-repo", "--ref", "HEAD", "--manifest-dir", w.mdir).returncode == 2
    assert w.verify("--base-commit", "zz").returncode == 2


def test_exit_1_on_malformed_files(tmp_path):
    w = World(tmp_path)
    (w.mdir / "manifest.json").write_text("{not json", encoding="utf-8")
    assert w.verify().returncode == 1
    w2 = World(tmp_path / "second")
    (w2.mdir / "transferred.tsv").write_bytes(b"wrong\theader\n")
    assert w2.verify().returncode == 1


def test_build_keeps_extra_rows_under_split_manifest(tmp_path):
    w = World(tmp_path)
    seed = tmp_path / "seed2.tsv"
    seed.write_bytes(tsv(vsm.HEADERS["additions.tsv"],
                         ADDITIONS + [("split-manifest/tools/x.py", "tools", "copy")]))
    mj = bsm.build(w.ev, seed, tmp_path / "o3", date="2026-10-11")
    rows = vsm.parse_tsv((tmp_path / "o3" / "additions.tsv").read_bytes(), "additions.tsv", vsm.Report())
    assert "split-manifest/tools/x.py" in [r[0] for r in rows]
    assert mj["counts"]["additions"] == len(ADDITIONS) + 6 + 1
