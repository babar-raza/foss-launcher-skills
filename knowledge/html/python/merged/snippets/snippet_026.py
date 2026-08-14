def test_public_exports():
    assert hasattr(enc, "detect_encoding")
    assert hasattr(enc, "EncodingDetectionResult")
    assert hasattr(enc, "UnsupportedEncodingError")