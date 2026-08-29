def test_pdf_padding_constant():
    """Check that PDF_PADDING matches PDF specification."""
    assert isinstance(PDF_PADDING, (bytes, bytearray)), "PDF_PADDING should be bytes"
    assert len(PDF_PADDING) == 32, "PDF_PADDING must be 32 bytes long"
    assert PDF_PADDING[:4] == bytes([0x28, 0xBF, 0x4E, 0x5E]), (
        "First four bytes incorrect"
    )