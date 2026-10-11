@Test
    void CV_21_doubleFormatsWithDecimal() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(1.5);
        assertEquals("1.5", cell.getStringValue());
    }