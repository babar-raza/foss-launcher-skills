@Test
    void valuePropertySetterMatchesSupportedScalarBehavior() {
        Workbook workbook = new Workbook();
        Worksheet sheet = workbook.getWorksheets().get(0);
        sheet.getCells().get("A1").setValue("alpha");
        sheet.getCells().get("B1").setValue(12);
        sheet.getCells().get("C1").setValue(true);
        sheet.getCells().get("D1").setValue(LocalDateTime.of(2024, 1, 2, 3, 4, 0));
        sheet.getCells().get("E1").setValue(null);

        assertEquals("alpha", sheet.getCells().get("A1").getValue());
        assertEquals(12, sheet.getCells().get("B1").getValue());
        assertEquals(true, sheet.getCells().get("C1").getValue());
        assertEquals(CellValueType.DATE_TIME, sheet.getCells().get("D1").getType());
        assertEquals("", sheet.getCells().get("E1").getDisplayStringValue());
    }