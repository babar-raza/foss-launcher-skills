@AfterEach
    void cleanup() {
        RgbPrintShift.clear();
        System.clearProperty("render.acrobatPrintParity");
        System.clearProperty("render.printParityRgbShift");
    }