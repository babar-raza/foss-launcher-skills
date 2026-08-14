@Test
    void AF_02_setRangePersists() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:E1");
            assertEquals("A1:E1", ws.getAutoFilter().getRange());
        }
    }