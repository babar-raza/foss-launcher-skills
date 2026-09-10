@Test
    void aPictureAddedFromAStreamMustResolveItsRelationship() throws Exception {
        Path out = tempDir.resolve("from-stream.pptx");
        try (var pres = new Presentation()) {
            IPPImage image;
            try (var in = new ByteArrayInputStream(Files.readAllBytes(JPEG))) {
                image = pres.getImages().addImage(in);
            }
            ISlide slide = pres.getSlides().get(0);
            slide.getShapes().addPictureFrame(ShapeType.RECTANGLE, 50, 50, 200, 150, image);
            pres.save(out.toString(), SaveFormat.PPTX);
        }
        assertPictureIsReachable(out, "jpeg", "jpg");
    }