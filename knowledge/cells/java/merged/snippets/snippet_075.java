@Test
    void CV_25_largeDoubleScientificNotation() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        double val = 6.02214076E+23;
        cell.putValue(val);
        assertEquals(CellValueType.NUMBER, cell.getType());
        assertEquals(val, (Double) cell.getValue(), 1e9);
    }