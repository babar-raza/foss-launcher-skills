@Test
    void AF_60_rangeRoundtripsViaXlsx() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af60.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getAutoFilter().setRange("A1:E1");
                wb.save(path);
            }
            try (Workbook loaded = new Workbook(path)) {
                assertEquals("A1:E1", loaded.getWorksheets().get(0).getAutoFilter().getRange());
            }
        }
    }