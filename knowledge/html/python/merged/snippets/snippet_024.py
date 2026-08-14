def test_public_api_doctest():
    import aspose_html.encoding.detection as mod
    results = doctest.testmod(mod, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest(s) failed in detection.py"