@Test
    void stringValueFormatsCorrectly() {
        Workbook workbook = new Workbook();
        Worksheet sheet = workbook.getWorksheets().get(0);
        sheet.getCells().get("A1").putValue("Hello");
        sheet.getCells().get("B1").putValue(123);
        sheet.getCells().get("C1").putValue(true);

        assertEquals("Hello", sheet.getCells().get("A1").getStringValue());
        assertEquals("123", sheet.getCells().get("B1").getStringValue());
        assertEquals("TRUE", sheet.getCells().get("C1").getStringValue());
        assertEquals("", sheet.getCells().get("D1").getStringValue());
    }