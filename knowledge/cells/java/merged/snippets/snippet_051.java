@Test
    void AF_71_xlsxContainsFilterColumnElement() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af71.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(2);
                wb.save(path);
            }
            String xml = ZipPackageHelper.readEntryText(path, "xl/worksheets/sheet1.xml");
            assertTrue(xml.contains("<filterColumn"), "Expected <filterColumn> element in sheet XML");
            assertTrue(xml.contains("colId=\"2\""), "Expected colId=\"2\" in filterColumn");
        }
    }