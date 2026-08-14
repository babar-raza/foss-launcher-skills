@Test
    void worksheetNotFoundThrowsCellsException() {
        Workbook workbook = new Workbook();
        assertThrows(CellsException.class, () -> workbook.getWorksheets().get("missing"));
    }