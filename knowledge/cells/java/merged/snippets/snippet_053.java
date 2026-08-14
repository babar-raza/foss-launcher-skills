@Test
    void AF_73_xlsxContainsCustomFiltersElement() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af73.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(0);
                ws.getAutoFilter().getFilterColumns().get(0).getCustomFilters()
                        .add(AutoFilterModel.FilterOperatorType.GREATER_THAN, "50");
                wb.save(path);
            }
            String xml = ZipPackageHelper.readEntryText(path, "xl/worksheets/sheet1.xml");
            assertTrue(xml.contains("<customFilters"), "Expected <customFilters> element in sheet XML");
            assertTrue(xml.contains("<customFilter"), "Expected <customFilter> element in sheet XML");
            assertTrue(xml.contains("val=\"50\""), "Expected val=\"50\" in customFilter element");
        }
    }