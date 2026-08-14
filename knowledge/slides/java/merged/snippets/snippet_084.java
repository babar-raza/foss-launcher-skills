@Test
    void testShapePersistsAfterReload() throws IOException {
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().get(0).getShapes().size()).isGreaterThanOrEqualTo(1);
                assertThat(pres2.getSlides().get(0).getShapes().get(0).getShapeType()).isEqualTo(ShapeType.RECTANGLE);
            }
        }
    }