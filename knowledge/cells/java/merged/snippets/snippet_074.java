@Test
    void CV_24_blankCellStringValueIsEmpty() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        assertEquals("", cell.getStringValue());
    }