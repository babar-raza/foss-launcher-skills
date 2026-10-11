@Test
    void AF_72_xlsxContainsFilterValueElements() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("AutoFilterTest")) {
            String path = tempDir.getPath("af72.xlsx");
            try (Workbook wb = new Workbook()) {
                Worksheet ws = wb.getWorksheets().get(0);
                ws.getAutoFilter().setRange("A1:D1");
                ws.getAutoFilter().getFilterColumns().add(0);
                ws.getAutoFilter().getFilterColumns().get(0).getFilters().add("Apple");
                ws.getAutoFilter().getFilterColumns().get(0).getFilters().add("Mango");
                wb.save(path);
            }
            String xml = ZipPackageHelper.readEntryText(path, "xl/worksheets/sheet1.xml");
            assertTrue(xml.contains("<filters"), "Expected <filters> element in sheet XML");
            assertTrue(xml.contains("val=\"Apple\""), "Expected val=\"Apple\" in filter element");
            assertTrue(xml.contains("val=\"Mango\""), "Expected val=\"Mango\" in filter element");
        }
    }