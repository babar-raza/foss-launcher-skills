@Test
    void CV_01_putValueString() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue("Hello");
        assertEquals("Hello", cell.getValue());
        assertEquals(CellValueType.STRING, cell.getType());
    }