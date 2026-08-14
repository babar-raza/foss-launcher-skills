@Test
    void alignmentPositionsMatchSpec() {
        // ISO/IEC 18004 Annex E centre coordinates for a sampling of versions.
        assertArrayEquals(new int[0], QrEncoder.alignmentPositions(1));
        assertArrayEquals(new int[]{6, 18}, QrEncoder.alignmentPositions(2));
        assertArrayEquals(new int[]{6, 22, 38}, QrEncoder.alignmentPositions(7));
        assertArrayEquals(new int[]{6, 26, 46}, QrEncoder.alignmentPositions(9));
        assertArrayEquals(new int[]{6, 30, 54}, QrEncoder.alignmentPositions(11));
        assertArrayEquals(new int[]{6, 26, 46, 66}, QrEncoder.alignmentPositions(14));
        assertArrayEquals(new int[]{6, 26, 50, 74}, QrEncoder.alignmentPositions(16));
        assertArrayEquals(new int[]{6, 34, 62, 90, 118}, QrEncoder.alignmentPositions(27));
        assertArrayEquals(new int[]{6, 34, 60, 86, 112, 138}, QrEncoder.alignmentPositions(32));
        assertArrayEquals(new int[]{6, 30, 58, 86, 114, 142, 170}, QrEncoder.alignmentPositions(40));
    }