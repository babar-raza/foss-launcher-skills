@Test
    void CV_10_setFormulaWithoutEqualNormalised() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.setFormula("A1+B1");
        assertEquals("=A1+B1", cell.getFormula());
    }