@Test
    void AF_64_customFilterAndLogicRoundtripsViaXlsx() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af64.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(0);
                AutoFilter.AutoFilterCustomFilterCollection cf =
                        ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
                cf.add(AutoFilterModel.FilterOperatorType.GREATER_THAN, "10");
                cf.add(AutoFilterModel.FilterOperatorType.LESS_THAN, "100");
                cf.setMatchAll(true);
                wb.save(path);
            }
            try (Workbook loaded = new Workbook(path)) {
                AutoFilter.AutoFilterCustomFilterCollection cf =
                        loaded.getWorksheets().get(0).getAutoFilter().getFilterColumns().get(0).getCustomFilters();
                assertEquals(2, cf.getCount());
                assertTrue(cf.isMatchAll());
            }
        }
    }