@Test
    void AF_42_setEnabledFalseDisablesDynamicFilter() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterDynamicFilter df =
                    ws.getAutoFilter().getFilterColumns().get(0).getDynamicFilter();
            df.setType("aboveAverage");
            assertTrue(df.isEnabled());
            df.setEnabled(false);
            assertFalse(df.isEnabled());
        }
    }