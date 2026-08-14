@Test
    void AF_65_top10RoundtripsViaXlsx() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af65.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(0);
                AutoFilter.AutoFilterTop10 top10 =
                        ws.getAutoFilter().getFilterColumns().get(0).getTop10();
                top10.setTop(true);
                top10.setValue(5.0);
                wb.save(path);
            }
            try (Workbook loaded = new Workbook(path)) {
                AutoFilter.AutoFilterTop10 top10 =
                        loaded.getWorksheets().get(0).getAutoFilter().getFilterColumns().get(0).getTop10();
                assertTrue(top10.isEnabled());
                assertTrue(top10.isTop());
                assertEquals(5.0, top10.getValue(), 1e-9);
            }
        }
    }