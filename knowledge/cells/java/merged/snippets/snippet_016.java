@Test
    void AF_11_filterColumnsInsertedInSortedOrder() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(2);
            ws.getAutoFilter().getFilterColumns().add(0);
            ws.getAutoFilter().getFilterColumns().add(1);
            assertEquals(0, ws.getAutoFilter().getFilterColumns().get(0).getFieldIndex());
            assertEquals(1, ws.getAutoFilter().getFilterColumns().get(1).getFieldIndex());
            assertEquals(2, ws.getAutoFilter().getFilterColumns().get(2).getFieldIndex());
        }
    }