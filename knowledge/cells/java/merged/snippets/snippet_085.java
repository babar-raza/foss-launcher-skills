@Test
    void CV_46_formulaTextRoundTrips() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("formulas.xlsx");
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getCells().get("A1").putValue(10);
                wb.getWorksheets().get(0).getCells().get("B1").setFormula("=A1*2");
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            assertEquals("=A1*2", loaded.getWorksheets().get(0).getCells().get("B1").getFormula());
        }
    }