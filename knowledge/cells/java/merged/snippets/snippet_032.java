@Test
    void AF_34_setOperatorOnCustomFilter() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterCustomFilterCollection cf =
                    ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
            cf.add(AutoFilterModel.FilterOperatorType.EQUAL, "100");
            cf.get(0).setOperator(AutoFilterModel.FilterOperatorType.NOT_EQUAL);
            assertEquals(AutoFilterModel.FilterOperatorType.NOT_EQUAL, cf.get(0).getOperator());
        }
    }