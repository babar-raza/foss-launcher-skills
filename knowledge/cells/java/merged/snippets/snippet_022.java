@Test
    void AF_17_negativeColumnIndexThrows() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            assertThrows(CellsException.class,
                    () -> ws.getAutoFilter().getFilterColumns().add(-1));
        }
    }