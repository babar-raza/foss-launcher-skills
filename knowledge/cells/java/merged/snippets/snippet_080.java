@Test
    void CV_41_integerRoundTripsWithoutBecomingDouble() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("basic.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getCells().get("A1").putValue(777);
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            String sv = loaded.getWorksheets().get(0).getCells().get("A1").getStringValue();
            assertFalse(sv.contains("."), "Integer string value should not contain a decimal point, was: " + sv);
        }
    }