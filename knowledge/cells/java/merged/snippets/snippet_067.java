@Test
    void CV_12_getTypeReturnsFormulaAfterFormulaSet() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(0);
        cell.setFormula("=1+1");
        assertEquals(CellValueType.FORMULA, cell.getType());
    }