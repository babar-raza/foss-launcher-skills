@Test
    void AF_70_xlsxContainsAutoFilterElement() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af70.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getAutoFilter().setRange("A1:D1");
                wb.save(path);
            }
            String xml = ZipPackageHelper.readEntryText(path, "xl/worksheets/sheet1.xml");
            assertTrue(xml.contains("<autoFilter"), "Expected <autoFilter> element in sheet XML");
            assertTrue(xml.contains("A1:D1"), "Expected ref attribute value A1:D1 in autoFilter");
        }
    }