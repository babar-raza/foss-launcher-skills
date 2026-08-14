@Test
    void AF_01_newWorksheetHasEmptyRange() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            String range = ws.getAutoFilter().getRange();
            assertTrue(range == null || range.isEmpty());
        }
    }