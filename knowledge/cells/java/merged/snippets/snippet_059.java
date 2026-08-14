@Test
    void CV_03_putValueDouble() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(3.14);
        assertEquals(3.14, (Double) cell.getValue(), 1e-9);
        assertEquals(CellValueType.NUMBER, cell.getType());
    }