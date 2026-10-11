@Test
    void CV_14_clearFormulaViaEmptyString() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.setFormula("=1+1");
        cell.setFormula("");
        cell.putValue(5);
        assertEquals("", cell.getFormula());
        assertEquals(CellValueType.NUMBER, cell.getType());
    }