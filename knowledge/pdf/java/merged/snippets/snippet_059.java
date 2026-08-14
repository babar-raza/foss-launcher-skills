@Test
    void cellAdd_multipleFields_appendsInOrder() throws Exception {
        try (Document doc = new Document()) {
            Page page = doc.getPages().add();
            Cell cell = new Cell();

            RadioButtonOptionField red = new RadioButtonOptionField(page,
                    new Rectangle(0, 0, 10, 10));
            red.setOptionName("Red");
            RadioButtonOptionField green = new RadioButtonOptionField(page,
                    new Rectangle(0, 0, 10, 10));
            green.setOptionName("Green");

            cell.add(red);
            cell.add(green);

            assertEquals(2, cell.getParagraphs().size());
            assertSame(red, ((FormFieldParagraph) cell.getParagraphs().get(0)).getField());
            assertSame(green, ((FormFieldParagraph) cell.getParagraphs().get(1)).getField());
        }
    }