@Test
    void worksheetCollectionActiveSheetName() {
        Workbook workbook = new Workbook();
        int idx = workbook.getWorksheets().add();
        workbook.getWorksheets().get(idx).setName("Report");
        workbook.getWorksheets().setActiveSheetName("Report");
        assertEquals(idx, workbook.getWorksheets().getActiveSheetIndex());
        assertEquals("Report", workbook.getWorksheets().getActiveSheetName());
    }