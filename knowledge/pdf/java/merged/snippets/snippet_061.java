@Test
    void cellAdd_nullArgs_throwIAE() {
        Cell cell = new Cell();
        assertThrows(IllegalArgumentException.class,
                () -> cell.add((RadioButtonOptionField) null));
        assertThrows(IllegalArgumentException.class,
                () -> cell.add((org.aspose.pdf.forms.Field) null));
        assertThrows(IllegalArgumentException.class,
                () -> cell.add((BaseParagraph) null));
    }