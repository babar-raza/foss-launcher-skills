@Test
    void CV_23_booleanFalseFormatsAsFALSE() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(false);
        assertEquals("FALSE", cell.getStringValue());
    }