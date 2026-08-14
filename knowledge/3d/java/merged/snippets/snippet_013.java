@Test
    public void detectStlFormatFromStreamWithFilename_ShouldReturnStlFormat() throws IOException {
        String testFile = "testdata/stl/stl_ascii.stl";

        File file = new File(testFile);
        if (!file.exists()) {
            throw new IOException("Test file not found: " + testFile);
        }

        FileInputStream stream = new FileInputStream(file);
        FileFormat format = FileFormat.detect(Stream.wrap(stream), "test.stl");
        stream.close();

        assertEquals("stl", format.getExtension());
    }