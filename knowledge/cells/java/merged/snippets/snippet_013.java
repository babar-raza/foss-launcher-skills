@Test
    void AF_03_setRangeNullClearsRange() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().setRange(null);
            String range = ws.getAutoFilter().getRange();
            assertTrue(range == null || range.isEmpty());
        }
    }