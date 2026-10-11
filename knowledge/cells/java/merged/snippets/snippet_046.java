@Test
    void AF_62_filterValuesRoundtripViaXlsx() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af62.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(0);
                ws.getAutoFilter().getFilterColumns().get(0).getFilters().add("Alpha");
                ws.getAutoFilter().getFilterColumns().get(0).getFilters().add("Beta");
                wb.save(path);
            }
            try (Workbook loaded = new Workbook(path)) {
                AutoFilter.FilterValueCollection fv =
                        loaded.getWorksheets().get(0).getAutoFilter().getFilterColumns().get(0).getFilters();
                assertEquals(2, fv.getCount());
                assertEquals("Alpha", fv.get(0));
                assertEquals("Beta", fv.get(1));
            }
        }
    }