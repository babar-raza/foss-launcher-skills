@Test
    void AF_15_filterColumnGetOutOfRangeThrows() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            assertThrows(CellsException.class,
                    () -> ws.getAutoFilter().getFilterColumns().get(0));
        }
    }