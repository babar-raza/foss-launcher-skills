@Test
    void AF_74_xlsxAndCombinedCustomFiltersHaveAndAttribute() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af74.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(0);
                AutoFilter.AutoFilterCustomFilterCollection cf =
                        ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters();
                cf.add(AutoFilterModel.FilterOperatorType.GREATER_THAN, "10");
                cf.add(AutoFilterModel.FilterOperatorType.LESS_THAN, "90");
                cf.setMatchAll(true);
                wb.save(path);
            }
            String xml = ZipPackageHelper.readEntryText(path, "xl/worksheets/sheet1.xml");
            assertTrue(xml.contains("and=\"1\""),
                    "Expected and=\"1\" attribute on <customFilters> for AND logic");
        }
    }