@Test
    void AF_13_removeAtFilterColumnDecrementsCount() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            ws.getAutoFilter().getFilterColumns().add(1);
            ws.getAutoFilter().getFilterColumns().removeAt(0);
            assertEquals(1, ws.getAutoFilter().getFilterColumns().getCount());
            assertEquals(1, ws.getAutoFilter().getFilterColumns().get(0).getFieldIndex());
        }
    }