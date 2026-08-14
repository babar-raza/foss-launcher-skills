@Test
    void CV_05_putValueBooleanFalse() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(false);
        assertEquals(false, cell.getValue());
        assertEquals(CellValueType.BOOLEAN, cell.getType());
    }