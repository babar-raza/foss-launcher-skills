@Test
    void generate_test_resources() throws Exception {
        Path cpInput = resolveClasspathInput();
        Path srcInput = Paths.get("src", "test", "resources", "Input");
        Files.createDirectories(cpInput);
        Files.createDirectories(srcInput);
        writeBytes(cpInput.resolve("pay.jpg"),    JPEG_1X1);
        writeBytes(srcInput.resolve("pay.jpg"),   JPEG_1X1);
        writeBytes(cpInput.resolve("screen.png"), PNG_1X1);
        writeBytes(srcInput.resolve("screen.png"),PNG_1X1);
        generateTableXlsx(cpInput, srcInput);
        generateCompareXlsx(cpInput, srcInput);
        generateShapeXlsx(cpInput, srcInput);
        generateChartDirs(cpInput, srcInput);
        generateAutofilterXlsx(cpInput, srcInput);
    }