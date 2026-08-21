@Test
    void inactiveWithoutParityFlag() {
        // the suite runs without -Drender.acrobatPrintParity — both switches off
        assertTrue(!CmykPrintLut.active() || Boolean.getBoolean("render.acrobatPrintParity"));
    }