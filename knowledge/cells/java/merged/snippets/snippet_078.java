@Test
    void CV_32_invalidAddressThrowsCellsException() {
        Workbook wb = new Workbook();
        Cells cells = wb.getWorksheets().get(0).getCells();
        assertThrows(CellsException.class, () -> cells.get("1A"));
    }