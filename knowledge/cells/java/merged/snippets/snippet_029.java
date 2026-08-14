@Test
    void AF_31_twoCustomFiltersWithOrLogic() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterCustomFilterCollection cf =
                    ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
            cf.add(AutoFilterModel.FilterOperatorType.GREATER_THAN, "10");
            cf.add(AutoFilterModel.FilterOperatorType.LESS_THAN, "50");
            assertEquals(2, cf.getCount());
            assertFalse(cf.isMatchAll());
        }
    }