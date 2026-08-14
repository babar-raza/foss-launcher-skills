@Test
    void AF_63_customFilterSingleRoundtripsViaXlsx() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af63.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(1);
                ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters()
                        .add(AutoFilterModel.FilterOperatorType.EQUAL, "42");
                wb.save(path);
            }
            try (Workbook loaded = new Workbook(path)) {
                AutoFilter.AutoFilterCustomFilterCollection cf =
                        loaded.getWorksheets().get(0).getAutoFilter().getFilterColumns().get(0).getCustomFilters();
                assertEquals(1, cf.getCount());
                assertEquals(AutoFilterModel.FilterOperatorType.EQUAL, cf.get(0).getOperator());
                assertEquals("42", cf.get(0).getValue());
            }
        }
    }