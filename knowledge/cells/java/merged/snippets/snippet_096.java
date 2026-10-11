@Test
    void exceptionMappingUsesCellsExceptionTypes() {
        assertThrows(CellsException.class, () -> new Workbook().getWorksheets().get("missing"));
        assertThrows(CellsException.class, () -> new Workbook().getWorksheets().get(0).getCells().get("1A"));
        assertThrows(InvalidFileFormatException.class,
                () -> new Workbook(new ByteArrayInputStream(new byte[]{1, 2, 3, 4})));
    }