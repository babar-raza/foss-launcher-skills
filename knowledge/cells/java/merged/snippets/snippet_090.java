@Test
    void publicTypeMappingMatchesCellValueTypes() {
        Workbook workbook = new Workbook();
        Worksheet sheet = workbook.getWorksheets().get(0);
        sheet.getCells().get("A1").putValue("Hello");
        sheet.getCells().get("B1").putValue(123);
        sheet.getCells().get("C1").putValue(true);
        sheet.getCells().get("D1").putValue(12.5d);
        sheet.getCells().get("F1").putValue(LocalDateTime.of(2024, 5, 6, 7, 8, 9));
        sheet.getCells().get("G1").setFormula("=B1*2");

        assertEquals(CellValueType.STRING, sheet.getCells().get("A1").getType());
        assertEquals(CellValueType.NUMBER, sheet.getCells().get("B1").getType());
        assertEquals(CellValueType.BOOLEAN, sheet.getCells().get("C1").getType());
        assertEquals(CellValueType.NUMBER, sheet.getCells().get("D1").getType());
        assertEquals(CellValueType.BLANK, sheet.getCells().get("E1").getType());
        assertEquals(CellValueType.DATE_TIME, sheet.getCells().get("F1").getType());
        assertEquals(CellValueType.FORMULA, sheet.getCells().get("G1").getType());
    }