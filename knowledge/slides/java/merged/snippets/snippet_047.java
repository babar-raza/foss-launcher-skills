@Test
    void testImageFromFile() throws IOException {
        Path testDataDir = Path.of("tests", "test_data");
        Path imgPath = testDataDir.resolve("lotus.png");
        assumeTrue(Files.exists(imgPath), "lotus.png not in test_data");

        try (Presentation pres = new Presentation()) {
            byte[] imgData = Files.readAllBytes(imgPath);
            IPPImage ppImg = pres.getImages().addImage(imgData);
            pres.getSlides().get(0).getShapes().addPictureFrame(
                    ShapeType.RECTANGLE, 50, 50, 200, 200, ppImg);
            assertThat(pres.getSlides().get(0).getShapes().size()).isGreaterThanOrEqualTo(1);
        }
    }