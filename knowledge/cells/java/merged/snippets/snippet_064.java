@Test
    void CV_08_setValueObjectDispatches() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        cell.setValue(99);
        cell.setValue("x");
        assertEquals(CellValueType.STRING, cell.getType());
        assertEquals("x", cell.getValue());
    }