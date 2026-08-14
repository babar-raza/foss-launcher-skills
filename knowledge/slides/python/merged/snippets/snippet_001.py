def test_data_dir():
    """Return the path to the tests/test_data/ directory."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")