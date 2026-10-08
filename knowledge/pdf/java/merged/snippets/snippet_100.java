@Test
    public void testImportMultipleAnnotationTypes() throws IOException {
        String xfdf = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                + "<xfdf xmlns=\"http://ns.adobe.com/xfdf/\">\n"
                + "  <annots>\n"
                + "    <text page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <highlight page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <underline page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <strikeout page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <squiggly page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <freetext page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <line page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <circle page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <square page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <ink page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <stamp page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <caret page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <polygon page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <polyline page=\"0\" rect=\"0,0,50,50\" />\n"
                + "    <redact page=\"0\" rect=\"0,0,50,50\" />\n"
                + "  </annots>\n"
                + "</xfdf>";

        Document doc = new Document();
        doc.getPages().add();
        importFromString(doc, xfdf);

        // 15 imported annotations + an auto-paired Popup for each markup type
        // except FreeText (Adobe/Aspose XFDF-import semantics) = 15 + 14
        assertEquals(29, doc.getPages().get(1).getAnnotations().size(),
                "Should import all 15 annotation types (+14 popups)");

        doc.close();
    }