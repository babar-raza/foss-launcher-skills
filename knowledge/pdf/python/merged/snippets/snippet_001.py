def test_font_embedding_success(tmp_path):
    # 1. Setup font lookup directory with a dummy font file
    font_dir = tmp_path / "fonts"
    font_dir.mkdir()
    font_file = font_dir / "MyTestFont.ttf"
    dummy_font_data = b"dummy ttf data"
    font_file.write_bytes(dummy_font_data)

    # 2. Load PDF with unembedded font
    pdf_bytes = _build_pdf_with_unembedded_font()
    doc = Document()
    doc.load_from(pdf_bytes)
    
    # Verify it fails PDF/A compliance check initially
    results = doc.validate_pdfa("1b")
    assert not results.is_valid
    assert any("MyTestFont" in err and "not embedded" in err for err in results.errors)

    # 3. Convert to PDF/A with font lookup directory
    doc.convert_to_pdfa("1b", font_lookup_directory=font_dir)

    # 4. Verify compliance and embedding
    results = doc.validate_pdfa("1b")
    # The font error should be GONE.
    assert not any("MyTestFont" in err and "not embedded" in err for err in results.errors), \
        f"Font still reported as not embedded: {results.errors}"

    # Verify PDF structure (FontDescriptor should have FontFile2)
    engine = doc._engine_pdf
    page_dict = engine._get_page_dict(0)
    res = engine._resolve(page_dict.get(PdfName("Resources")))
    fonts = engine._resolve(res.get(PdfName("Font")))
    font = engine._resolve(fonts.get(PdfName("F1")))
    descriptor = engine._resolve(font.get(PdfName("FontDescriptor")))
    
    assert PdfName("FontFile2") in descriptor
    font_stream = engine._resolve(descriptor.get(PdfName("FontFile2")))
    assert font_stream.content == dummy_font_data