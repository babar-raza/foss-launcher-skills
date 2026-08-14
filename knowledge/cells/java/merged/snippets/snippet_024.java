@Test
    void AF_21_multipleFilterValuesAddedAndRetrieved() throws Exception {
        // Wrap lower-level failures in the library-specific exception flow.
        try (Workbook wb = new Workbook()) {
            Worksheet ws = wb.getWorksheets().get(0);
            ws.getAutoFilter().setRange("A1:D1");
            ws.getAutoFilter().getFilterColumns().add(0);
            AutoFilter.FilterValueCollection fv =
                    ws.getAutoFilter().getFilterColumns().get(0).getFilters();
            fv.add("Apple");
            fv.add("Banana");
            fv.add("Cherry");
            assertEquals(3, fv.getCount());
            assertEquals("Apple", fv.get(0));
            assertEquals("Banana", fv.get(1));
            assertEquals("Cherry", fv.get(2));
        }
    }