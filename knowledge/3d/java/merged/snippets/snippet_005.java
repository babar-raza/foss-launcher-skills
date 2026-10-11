@Test
    public void detectObjFormatFromStream_ShouldReturnObjFormat() throws IOException {
        String testFile = "testdata/input/cube.obj";

        File file = new File(testFile);
        if (!file.exists()) {
            throw new IOException("Test file not found: " + testFile);
        }

        FileInputStream stream = new FileInputStream(file);
        FileFormat format = FileFormat.detect(Stream.wrap(stream), "cube.obj");
        stream.close();

        assertEquals("obj", format.getExtension());
    }