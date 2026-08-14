@Test
    void AF_40_dynamicFilterDefaultDisabled() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            assertFalse(ws.getAutoFilter().getFilterColumns().get(0).getDynamicFilter().isEnabled());
        }
    }