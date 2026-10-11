@Test
    void CV_43_booleanRoundTrips() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("basic.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getCells().get("A1").putValue(true);
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            Cell cell = loaded.getWorksheets().get(0).getCells().get("A1");
            assertEquals(CellValueType.BOOLEAN, cell.getType());
            assertEquals(true, cell.getValue());
        }
    }