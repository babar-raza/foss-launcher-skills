@Test
    void CV_40_stringRoundTripsThroughXlsx() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("basic.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getCells().get("A1").putValue("RoundTrip");
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            assertEquals("RoundTrip", loaded.getWorksheets().get(0).getCells().get("A1").getValue());
        }
    }