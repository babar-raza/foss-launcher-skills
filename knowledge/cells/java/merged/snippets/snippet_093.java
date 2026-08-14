@Test
    void worksheetCollectionAddAndGet() {
        Workbook workbook = new Workbook();
        assertEquals(1, workbook.getWorksheets().getCount());

        int idx = workbook.getWorksheets().add();
        assertEquals(2, workbook.getWorksheets().getCount());

        workbook.getWorksheets().get(idx).setName("Report");
        assertEquals("Report", workbook.getWorksheets().get(idx).getName());
        assertEquals("Report", workbook.getWorksheets().get("Report").getName());
    }