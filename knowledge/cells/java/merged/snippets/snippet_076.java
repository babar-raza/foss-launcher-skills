@Test
    void CV_30_getCellsGetStringAcceptsA1Notation() {
        Workbook wb = new Workbook();
        Cells cells = wb.getWorksheets().get(0).getCells();
        cells.get("A1").putValue(1);
        assertEquals(1, cells.get("A1").getValue());
    }