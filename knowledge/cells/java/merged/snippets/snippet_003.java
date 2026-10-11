private static Path resolveClasspathInput() throws Exception {
        URL root = AResourceGeneratorTest.class.getClassLoader().getResource(".");
        if (root != null) { return Paths.get(root.toURI()).resolve("Input"); }
        return Paths.get("target", "test-classes", "Input");
    }