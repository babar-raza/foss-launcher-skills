@Test
    void testSoftEdge() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 100, 100, 200, 100);
            var ef = shape.getEffectFormat();
            ef.enableSoftEdgeEffect();
            ef.getSoftEdgeEffect().setRadius(10);

            try (var pres2 = saveAndReopen(pres)) {
                var se2 = pres2.getSlides().get(0).getShapes().get(0).getEffectFormat().getSoftEdgeEffect();
                assertThat(se2).as("soft_edge_effect should not be None after reload").isNotNull();
                assertThat(se2.getRadius()).isEqualTo(10);
            }
        }
    }