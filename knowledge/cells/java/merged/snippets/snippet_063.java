@Test
    void CV_07_setValueNullClearsCell() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue("something");
        cell.setValue(null);
        assertEquals(CellValueType.BLANK, cell.getType());
        assertEquals("", cell.getStringValue());
    }