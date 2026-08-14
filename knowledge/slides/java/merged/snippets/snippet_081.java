@Test
    void testShapeFrameProperties() throws IOException {
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 200, 200, 300, 250);
            shape.setRotation(45);

            try (var pres2 = saveAndReopen(pres)) {
                var s2 = pres2.getSlides().get(0).getShapes().get(0);
                assertThat(s2.getX()).isEqualTo(200);
                assertThat(s2.getY()).isEqualTo(200);
                assertThat(s2.getWidth()).isEqualTo(300);
                assertThat(s2.getHeight()).isEqualTo(250);
                assertThat(s2.getRotation()).isEqualTo(45);
            }
        }
    }