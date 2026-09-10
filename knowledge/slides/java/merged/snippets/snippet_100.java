@Test
    void testOuterShadow() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 100, 100, 200, 100);
            var ef = shape.getEffectFormat();
            ef.enableOuterShadowEffect();
            var shadow = ef.getOuterShadowEffect();
            shadow.setBlurRadius(10);
            shadow.setDirection(315);
            shadow.setDistance(8);
            shadow.getShadowColor().setColor(Color.fromArgb(128, 0, 0, 0));

            try (var pres2 = saveAndReopen(pres)) {
                var ef2 = pres2.getSlides().get(0).getShapes().get(0).getEffectFormat();
                var s2 = ef2.getOuterShadowEffect();
                assertThat(s2).as("outer_shadow_effect should not be None after reload").isNotNull();
                assertThat(s2.getBlurRadius()).isEqualTo(10);
                assertThat(s2.getDirection()).isEqualTo(315);
                assertThat(s2.getDistance()).isEqualTo(8);
            }
        }
    }