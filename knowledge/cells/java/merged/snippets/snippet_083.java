@Test
    void CV_44_dateTimeRoundTrips1900System() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (TemporaryDirectory tempDir = new TemporaryDirectory("CellValueTest")) {
            String path = tempDir.getPath("dates.xlsx");
            LocalDateTime dt = LocalDateTime.of(2024, 3, 15, 10, 30, 0);
            try (Workbook wb = new Workbook()) {
                wb.getWorksheets().get(0).getCells().get("A1").putValue(dt);
                wb.save(path);
            }
            Workbook loaded = new Workbook(path);
            Cell cell = loaded.getWorksheets().get(0).getCells().get("A1");
            assertEquals(CellValueType.DATE_TIME, cell.getType());
            LocalDateTime loaded_dt = (LocalDateTime) cell.getValue();
            assertEquals(dt.getYear(), loaded_dt.getYear());
            assertEquals(dt.getMonth(), loaded_dt.getMonth());
            assertEquals(dt.getDayOfMonth(), loaded_dt.getDayOfMonth());
            assertEquals(dt.getHour(), loaded_dt.getHour());
            assertEquals(dt.getMinute(), loaded_dt.getMinute());
            assertEquals(dt.getSecond(), loaded_dt.getSecond());
        }
    }