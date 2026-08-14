@Test
    void ctor_nullCatalog_throws() {
        assertThrows(IllegalArgumentException.class, () -> new DocumentActions(null, null));
    }