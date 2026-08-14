@Test
    void AF_20_addFilterValueReturnsIndex() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            int idx = ws.getAutoFilter().getFilterColumns().get(0).getFilters().add("Apple");
            assertEquals(0, idx);
            assertEquals(1, ws.getAutoFilter().getFilterColumns().get(0).getFilters().getCount());
        }
    }