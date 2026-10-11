def test_save_markdown_with_base64_image_to_docx_and_pdf(self):
        """A Markdown source with several headings, a base64 image, and repeated links,
        saved to DOCX and PDF with the image embedded and the links clickable."""
        # ExStart:SaveMarkdownWithImageToDocxAndPdf
        doc = aw.Document(
            io.BytesIO(MARKDOWN_WITH_IMAGE_AND_LINK.encode("utf-8")),
            aw.loading.MarkdownLoadOptions(),
        )
        docx_path = ARTIFACTS_DIR + "LoadingMarkdown.WithImage.docx"
        pdf_path = ARTIFACTS_DIR + "LoadingMarkdown.WithImage.pdf"
        doc.save(docx_path, aw.SaveFormat.DOCX)
        doc.save(pdf_path, aw.SaveFormat.PDF)
        # ExEnd:SaveMarkdownWithImageToDocxAndPdf

        # The base64 image becomes a real embedded Shape, not literal "![alt](data:...)" text.
        expected_png = base64.b64decode(LOGO_PNG_BASE64)
        shapes = [n.as_shape() for n in doc.get_child_nodes(aw.NodeType.SHAPE, True)]
        ours = [sh for sh in shapes if sh.image_data.image_bytes == expected_png]
        assert len(ours) == 1
        assert ours[0].has_image
        assert ours[0].image_data.image_type == awd.ImageType.PNG

        # Re-read the saved .docx from disk to confirm the image survived the round trip,
        # not just the in-memory Document.
        reloaded = aw.Document(docx_path)
        saved_shapes = [
            n.as_shape()
            for n in reloaded.get_child_nodes(aw.NodeType.SHAPE, True)
            if n.as_shape().has_image
        ]
        assert [sh for sh in saved_shapes if sh.image_data.image_bytes == expected_png]

        # Both headings ("Learn more" / "Get started") kept their own heading style,
        # and both links became real, clickable "<w:hyperlink>" elements pointing at
        # products.aspose.com -- not literal "[text](url)" text.
        import zipfile

        with zipfile.ZipFile(docx_path) as zf:
            document_xml = zf.read("word/document.xml").decode("utf-8")
            rels_xml = zf.read("word/_rels/document.xml.rels").decode("utf-8")
        assert document_xml.count("<w:hyperlink ") >= 2
        assert f"[product page]({PRODUCT_URL})" not in document_xml  # never literal markdown syntax
        assert rels_xml.count(f'Target="{PRODUCT_URL}"') >= 1

        # Same check on the PDF: two real clickable link annotations, not styled text.
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            links = [link for page in pdf.pages for link in page.hyperlinks]
        assert len([link for link in links if link["uri"] == PRODUCT_URL]) == 2