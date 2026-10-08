@Test
    void setEndingStyle_nullOrNone_removesEntry() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            FreeTextAnnotation ft = new FreeTextAnnotation(p, new Rectangle(0, 0, 100, 50));
            ft.setEndingStyle(LineEnding.Square);
            assertNotNull(ft.getPdfDictionary().get("LE"));

            ft.setEndingStyle(null);
            assertNull(ft.getPdfDictionary().get("LE"));

            ft.setEndingStyle(LineEnding.Butt);
            assertNotNull(ft.getPdfDictionary().get("LE"));
            ft.setEndingStyle(LineEnding.None);
            assertNull(ft.getPdfDictionary().get("LE"));
        }
    }