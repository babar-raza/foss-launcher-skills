@Test
    void CV_42_doubleRoundTrips() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("basic.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getCells().get("A1").putValue(2.71828);
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            assertEquals(2.71828, (Double) loaded.getWorksheets().get(0).getCells().get("A1").getValue(), 1e-9);
        }
    }