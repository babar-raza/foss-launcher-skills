@Test
    void CV_04_putValueBooleanTrue() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(true);
        assertEquals(true, cell.getValue());
        assertEquals(CellValueType.BOOLEAN, cell.getType());
    }