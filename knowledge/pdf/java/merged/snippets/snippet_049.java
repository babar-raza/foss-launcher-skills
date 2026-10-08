@Test
    void setEndingStyle_roundTrips() throws Exception {
        try (Document doc = new Document()) {
            Page p = doc.getPages().add();
            FreeTextAnnotation ft = new FreeTextAnnotation(p, new Rectangle(0, 0, 100, 50));
            ft.setEndingStyle(LineEnding.OpenArrow);
            assertEquals(LineEnding.OpenArrow, ft.getEndingStyle());

            ft.setEndingStyle(LineEnding.Diamond);
            assertEquals(LineEnding.Diamond, ft.getEndingStyle());
        }
    }