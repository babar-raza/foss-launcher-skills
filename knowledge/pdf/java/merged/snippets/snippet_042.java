@Test
    void subtype_isWatermark() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            WatermarkAnnotation w = new WatermarkAnnotation(p, new Rectangle(0, 0, 100, 100));
            // Verify the /Subtype entry was set
            assertEquals("Watermark",
                    ((org.aspose.pdf.engine.pdfobjects.PdfName) w.getPdfDictionary().get("Subtype")).getName());
        }
    }