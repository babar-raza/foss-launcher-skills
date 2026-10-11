@Test
    void CV_06_putValueLocalDateTime() {
        Workbook wb = new Workbook();
        Cell cell = wb.getWorksheets().get(0).getCells().get("A1");
        LocalDateTime dt = LocalDateTime.of(2024, 5, 6, 7, 8, 9);
        cell.putValue(dt);
        assertEquals(CellValueType.DATE_TIME, cell.getType());
        assertEquals(dt, cell.getValue());
    }