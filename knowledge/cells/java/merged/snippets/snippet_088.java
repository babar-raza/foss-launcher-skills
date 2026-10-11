@Test
    void formulaSetterAcceptsWithOrWithoutLeadingEqual() {
        Workbook workbook = new Workbook();
        Cell cell = workbook.getWorksheets().get(0).getCells().get("A1");
        cell.putValue(10);
        cell.setFormula("B1+C1");
        assertEquals("=B1+C1", cell.getFormula());

        cell.setFormula("=D1+E1");
        assertEquals("=D1+E1", cell.getFormula());
    }