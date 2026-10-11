@Test
    void AF_53_setValuePersistsAndEnables() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterTop10 top10 =
                    ws.getAutoFilter().getFilterColumns().get(0).getTop10();
            top10.setValue(5.0);
            assertTrue(top10.isEnabled());
            assertEquals(5.0, top10.getValue(), 1e-9);
        }
    }