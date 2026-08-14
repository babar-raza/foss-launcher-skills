@Test
    void AF_75_xlsxContainsTop10Element() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af75.xlsx");
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
            String xml = ZipPackageHelper.readEntryText(path, "xl/worksheets/sheet1.xml");
            assertTrue(xml.contains("<top10"), "Expected <top10> element in sheet XML");
            assertTrue(xml.contains("top=\"1\""), "Expected top=\"1\" in top10 element");
            assertTrue(xml.contains("val=\"5.0\""), "Expected val=\"5.0\" in top10 element");
        }
    }