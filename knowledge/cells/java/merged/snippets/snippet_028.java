@Test
    void AF_30_addSingleCustomFilter() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterCustomFilterCollection cf =
                    ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
            int idx = cf.add(AutoFilterModel.FilterOperatorType.EQUAL, "100");
            assertEquals(0, idx);
            assertEquals(1, cf.getCount());
            assertEquals(AutoFilterModel.FilterOperatorType.EQUAL, cf.get(0).getOperator());
            assertEquals("100", cf.get(0).getValue());
        }
    }