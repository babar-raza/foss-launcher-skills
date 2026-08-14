@Test
    void AF_61_filterColumnIndexRoundtripsViaXlsx() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af61.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(2);
                wb.save(path);
            }
            try (Workbook loaded = new Workbook(path)) {
                assertEquals(1, loaded.getWorksheets().get(0).getAutoFilter().getFilterColumns().getCount());
                assertEquals(2, loaded.getWorksheets().get(0).getAutoFilter().getFilterColumns().get(0).getFieldIndex());
            }
        }
    }