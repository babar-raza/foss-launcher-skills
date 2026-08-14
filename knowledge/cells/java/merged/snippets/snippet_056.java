@Test
    void AF_76_xlsxContainsHiddenButtonAttribute() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af76.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(0);
                ws.getAutoFilter().getFilterColumns().get(0).setDropdownVisible(false);
                wb.save(path);
            }
            String xml = ZipPackageHelper.readEntryText(path, "xl/worksheets/sheet1.xml");
            assertTrue(xml.contains("hiddenButton=\"1\""),
                    "Expected hiddenButton=\"1\" in filterColumn element");
        }
    }