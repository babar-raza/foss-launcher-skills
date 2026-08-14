@Test
    void CV_45_dateTimeRoundTrips1904System() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("dates-1904.xlsx");
            LocalDateTime dt = LocalDateTime.of(2024, 6, 1, 12, 0, 0);
            try (Workbook wb = new Workbook()) {
                wb.getSettings().setDate1904(true);
                wb.getWorksheets().get(0).getCells().get("A1").putValue(dt);
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            assertTrue(loaded.getSettings().getDate1904());
            Cell cell = loaded.getWorksheets().get(0).getCells().get("A1");
            assertEquals(CellValueType.DATE_TIME, cell.getType());
            LocalDateTime loaded_dt = (LocalDateTime) cell.getValue();
            assertEquals(dt.getYear(), loaded_dt.getYear());
            assertEquals(dt.getMonth(), loaded_dt.getMonth());
            assertEquals(dt.getDayOfMonth(), loaded_dt.getDayOfMonth());
        }
    }