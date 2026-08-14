@Test
    void CV_02_putValueInt() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(42);
        assertEquals(42, cell.getValue());
        assertEquals(CellValueType.NUMBER, cell.getType());
    }