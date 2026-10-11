@Test
    void AF_10_addFilterColumnReturnsIndex() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            int idx = ws.getAutoFilter().getFilterColumns().add(0);
            assertEquals(0, idx);
            assertEquals(1, ws.getAutoFilter().getFilterColumns().getCount());
        }
    }