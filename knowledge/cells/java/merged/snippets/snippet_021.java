@Test
    void AF_16_filterColumnRemoveAtOutOfRangeThrows() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            assertThrows(CellsException.class,
                    () -> ws.getAutoFilter().getFilterColumns().removeAt(0));
        }
    }