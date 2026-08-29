def test_bundle_is_deterministic() -> None:
    """The checked-in bundle matches a fresh build (SHA-verified generator)."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_agl_data.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout