@Test
    void CV_22_booleanTrueFormatsAsTRUE() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(true);
        assertEquals("TRUE", cell.getStringValue());
    }