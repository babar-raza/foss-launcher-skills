@Test
    void AF_36_customFilterClearResetsState() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterCustomFilterCollection cf =
                    ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
            cf.add(AutoFilterModel.FilterOperatorType.EQUAL, "A");
            cf.add(AutoFilterModel.FilterOperatorType.EQUAL, "B");
            cf.setMatchAll(true);
            cf.clear();
            assertEquals(0, cf.getCount());
            assertFalse(cf.isMatchAll());
        }
    }