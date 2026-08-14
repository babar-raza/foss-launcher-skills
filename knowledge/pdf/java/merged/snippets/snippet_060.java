@Test
    void cellAdd_alongsideRegularParagraph_mixed() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            Cell cell = new Cell();

            cell.add(new org.aspose.pdf.text.TextFragment("Choose:"));

            RadioButtonOptionField red = new RadioButtonOptionField(page,
                    new Rectangle(0, 0, 10, 10));
            red.setOptionName("Red");
            cell.add(red);

            assertEquals(2, cell.getParagraphs().size());
            assertTrue(cell.getParagraphs().get(0) instanceof org.aspose.pdf.text.TextFragment);
            assertTrue(cell.getParagraphs().get(1) instanceof FormFieldParagraph);
        }
    }