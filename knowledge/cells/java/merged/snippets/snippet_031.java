@Test
    void AF_33_thirdCustomFilterThrows() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.AutoFilterCustomFilterCollection cf =
                    ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
            cf.add(AutoFilterModel.FilterOperatorType.EQUAL, "A");
            cf.add(AutoFilterModel.FilterOperatorType.EQUAL, "B");
            assertThrows(CellsException.class,
                    () -> cf.add(AutoFilterModel.FilterOperatorType.EQUAL, "C"));
        }
    }