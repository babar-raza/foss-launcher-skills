@Test
    void AF_32_twoCustomFiltersWithAndLogic() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterCustomFilterCollection cf =
                    ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
            cf.add(AutoFilterModel.FilterOperatorType.GREATER_OR_EQUAL, "10");
            cf.add(AutoFilterModel.FilterOperatorType.LESS_OR_EQUAL, "50");
            cf.setMatchAll(true);
            assertTrue(cf.isMatchAll());
            assertEquals(2, cf.getCount());
        }
    }