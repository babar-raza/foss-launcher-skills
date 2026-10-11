@Test
    void AF_14_filterColumnsClearRemovesAll() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            ws.getAutoFilter().getFilterColumns().add(1);
            ws.getAutoFilter().getFilterColumns().clear();
            assertEquals(0, ws.getAutoFilter().getFilterColumns().getCount());
        }
    }