@Test
    void CV_20_integerFormatsWithoutDecimal() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(123);
        assertEquals("123", cell.getStringValue());
    }