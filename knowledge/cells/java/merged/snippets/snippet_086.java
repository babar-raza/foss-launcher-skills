@Test
    void CV_47_multiSheetValuesRoundTrip() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("multi.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).setName("Sheet1");
                wb.getWorksheets().get(0).getCells().get("A1").putValue("Alpha");
                wb.getWorksheets().add("Sheet2");
                wb.getWorksheets().get(1).getCells().get("A1").putValue("Beta");
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            assertEquals("Alpha", loaded.getWorksheets().get(0).getCells().get("A1").getValue());
            assertEquals("Beta", loaded.getWorksheets().get(1).getCells().get("A1").getValue());
        }
    }