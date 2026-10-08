@Test
    public void enum_toFromPdfName_roundtrip() {
        assertEquals("FreeText", FreeTextIntent.FreeText.toPdfName());
        assertEquals("FreeTextCallout", FreeTextIntent.FreeTextCallout.toPdfName());
        assertEquals("FreeTextTypeWriter", FreeTextIntent.FreeTextTypeWriter.toPdfName());
        assertNull(FreeTextIntent.Undefined.toPdfName());

        assertEquals(FreeTextIntent.FreeText, FreeTextIntent.fromPdfName("FreeText"));
        assertEquals(FreeTextIntent.FreeTextCallout, FreeTextIntent.fromPdfName("FreeTextCallout"));
        assertEquals(FreeTextIntent.FreeTextTypeWriter, FreeTextIntent.fromPdfName("FreeTextTypeWriter"));
        assertEquals(FreeTextIntent.Undefined, FreeTextIntent.fromPdfName(null));
        assertEquals(FreeTextIntent.Undefined, FreeTextIntent.fromPdfName("Bogus"));
    }