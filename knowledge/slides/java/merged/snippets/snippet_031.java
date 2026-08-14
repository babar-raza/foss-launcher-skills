@Test
    void testBlur() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 100, 100, 200, 100);
            var ef = shape.getEffectFormat();
            ef.setBlurEffect(8, true);

            try (var pres2 = saveAndReopen(pres)) {
                var b2 = pres2.getSlides().get(0).getShapes().get(0).getEffectFormat().getBlurEffect();
                assertThat(b2).as("blur_effect should not be None after reload").isNotNull();
                assertThat(b2.getRadius()).isEqualTo(8);
            }
        }
    }