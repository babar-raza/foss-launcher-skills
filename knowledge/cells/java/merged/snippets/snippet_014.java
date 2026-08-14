@Test
    void AF_04_clearResetsRangeAndColumns() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            ws.getAutoFilter().clear();
            String range = ws.getAutoFilter().getRange();
            assertTrue(range == null || range.isEmpty());
            assertEquals(0, ws.getAutoFilter().getFilterColumns().getCount());
        }
    }