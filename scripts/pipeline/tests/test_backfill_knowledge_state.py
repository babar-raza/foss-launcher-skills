"""MT030-2026-08-13: backfill_knowledge_state.py -- one-time knowledge_state.json seed."""
import pytest
import yaml

# sys.path is set by tests/conftest.py
import backfill_knowledge_state as bks


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    import knowledge_state as ks
    monkeypatch.setattr(ks, "_STATE_PATH", tmp_path / "knowledge_state.json")
    monkeypatch.setattr(ks, "_LOCK_PATH", tmp_path / "knowledge_state.json.lock")
    self_ks = ks
    yield self_ks


def _write_model(knowledge_root, family, platform, repo_sha):
    merged_dir = knowledge_root / family / platform / "merged"
    merged_dir.mkdir(parents=True)
    (merged_dir / "model.yaml").write_text(
        yaml.safe_dump({"family": family, "platform": platform, "repo_sha": repo_sha}),
        encoding="utf-8",
    )
    return merged_dir


class TestDiscoverProducts:
    def test_finds_products_with_model_yaml(self, tmp_path):
        _write_model(tmp_path, "pdf", "java", "sha1")
        _write_model(tmp_path, "3d", "net", "sha2")
        products = bks.discover_products(tmp_path)
        assert set(products) == {("pdf", "java"), ("3d", "net")}

    def test_ignores_platform_dir_without_model_yaml(self, tmp_path):
        (tmp_path / "pdf" / "java" / "scout").mkdir(parents=True)  # scout/ only, no merged/
        products = bks.discover_products(tmp_path)
        assert products == []

    def test_missing_knowledge_root_returns_empty(self, tmp_path):
        assert bks.discover_products(tmp_path / "nonexistent") == []


class TestBackfillOne:
    def test_backfills_from_model_yaml_only(self, tmp_path, _isolate):
        _write_model(tmp_path, "pdf", "java", "be089a7e5179")
        result = bks.backfill_one("pdf", "java", tmp_path)
        assert result["repo_sha"] == "be089a7e5179"
        state = _isolate.read_state("pdf", "java")
        assert state["accepted_baseline"]["repo_sha"] == "be089a7e5179"
        assert state["accepted_baseline"]["sha_source"] == "backfill"

    def test_prefers_ledger_data_when_present(self, tmp_path, _isolate):
        merged_dir = _write_model(tmp_path, "pdf", "java", "be089a7e5179")
        (merged_dir / "baseline_ledger.jsonl").write_text(
            '{"run_id": "promote-20260729T164123Z", "new_repo_sha": "be089a7e5179", '
            '"sha_source": "scout", "status": "accepted", "accepted_at": "2026-07-29T16:41:23Z"}\n',
            encoding="utf-8",
        )
        result = bks.backfill_one("pdf", "java", tmp_path)
        assert result["sha_source"] == "scout"
        state = _isolate.read_state("pdf", "java")
        assert state["accepted_baseline"]["run_id"] == "promote-20260729T164123Z"
        assert state["accepted_baseline"]["accepted_at"] == "2026-07-29T16:41:23Z"

    def test_returns_none_when_no_repo_sha(self, tmp_path):
        merged_dir = tmp_path / "pdf" / "java" / "merged"
        merged_dir.mkdir(parents=True)
        (merged_dir / "model.yaml").write_text(yaml.safe_dump({"family": "pdf"}), encoding="utf-8")
        assert bks.backfill_one("pdf", "java", tmp_path) is None

    def test_returns_none_when_model_missing(self, tmp_path):
        assert bks.backfill_one("nonexistent", "platform", tmp_path) is None

    def test_idempotent_rerun_with_ledger(self, tmp_path, _isolate):
        """Byte-identical reruns require a stable accepted_at -- only guaranteed
        when a baseline_ledger.jsonl entry supplies one. The model.yaml-only
        fallback path legitimately stamps a fresh 'now' each call (no better
        historical data exists), so it is not tested for byte-identity here."""
        merged_dir = _write_model(tmp_path, "pdf", "java", "sha1")
        (merged_dir / "baseline_ledger.jsonl").write_text(
            '{"run_id": "run1", "new_repo_sha": "sha1", "sha_source": "scout", '
            '"status": "accepted", "accepted_at": "2026-01-01T00:00:00Z"}\n',
            encoding="utf-8",
        )
        bks.backfill_one("pdf", "java", tmp_path)
        first = _isolate._STATE_PATH.read_text(encoding="utf-8")
        bks.backfill_one("pdf", "java", tmp_path)
        second = _isolate._STATE_PATH.read_text(encoding="utf-8")
        assert first == second


class TestMain:
    def test_dry_run_does_not_write_state(self, tmp_path, _isolate, monkeypatch, capsys):
        _write_model(tmp_path, "pdf", "java", "sha1")
        monkeypatch.setattr(bks, "KNOWLEDGE_ROOT", tmp_path)
        exit_code = bks.main(["--dry-run"])
        assert exit_code == 0
        assert _isolate.read_state("pdf", "java") is None
        captured = capsys.readouterr()
        assert "would backfill 1/1" in captured.out

    def test_real_run_writes_state(self, tmp_path, _isolate, monkeypatch):
        _write_model(tmp_path, "pdf", "java", "sha1")
        monkeypatch.setattr(bks, "KNOWLEDGE_ROOT", tmp_path)
        exit_code = bks.main([])
        assert exit_code == 0
        assert _isolate.read_state("pdf", "java") is not None

    def test_no_products_found_exits_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bks, "KNOWLEDGE_ROOT", tmp_path / "nonexistent")
        assert bks.main([]) == 0
