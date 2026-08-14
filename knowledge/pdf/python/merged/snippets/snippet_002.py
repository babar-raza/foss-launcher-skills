def test_font_embedding_missing_file(tmp_path):
    # Empty font directory
    font_dir = tmp_path / "empty_fonts"
    font_dir.mkdir()

    pdf_bytes = _build_pdf_with_unembedded_font()
    doc = Document()
    doc.load_from(pdf_bytes)
    
    # Convert without the right font in directory
    remaining = doc.convert_to_pdfa("1b", font_lookup_directory=font_dir)
    
    # Should still report the font issue
    assert any("MyTestFont" in err and "not embedded" in err for err in remaining)