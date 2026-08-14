@Test
    void CV_13_cachedFormulaValuePersists() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(20);
        cell.setFormula("=B1*2");
        // Cached value from putValue(20) should remain as string value
        assertEquals("20", cell.getStringValue());
    }