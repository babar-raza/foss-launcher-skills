@Test
    void testPictureFrame() throws IOException {
        try (var pres = new Presentation()) {
            IPPImage img = pres.getImages().addImage(createTestPng(0, 0, 255));
            pres.getSlides().get(0).getShapes().addPictureFrame(
                    ShapeType.RECTANGLE, 50, 50, 100, 100, img);
            assertThat(pres.getSlides().get(0).getShapes().size()).isGreaterThanOrEqualTo(1);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().get(0).getShapes().size()).isGreaterThanOrEqualTo(1);
            }
        }
    }