@Test
    void AF_37_blankCustomFilterValueAccepted() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterCustomFilterCollection cf =
                    ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
            assertDoesNotThrow(
                    () -> cf.add(AutoFilterModel.FilterOperatorType.EQUAL, ""));
            assertEquals(1, cf.getCount());
        }
    }