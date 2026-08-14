@Test
    void missingDirNeverThrows() {
        byte[] found = FontDiskLookup.loadStyled("TestFont", true, true,
                new String[]{"Z:/no/such/dir/anywhere"});
        // may be null (not on host) — the point is it does not throw
        assertTrue(found == null || found.length > 0, "missing dir handled gracefully");
    }