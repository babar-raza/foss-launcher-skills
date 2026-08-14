@Test
    void testGlow() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.ELLIPSE, 100, 100, 200, 200);
            var ef = shape.getEffectFormat();
            ef.enableGlowEffect();
            ef.getGlowEffect().setRadius(15);
            ef.getGlowEffect().getColor().setColor(Color.GOLD);

            try (var pres2 = saveAndReopen(pres)) {
                var g2 = pres2.getSlides().get(0).getShapes().get(0).getEffectFormat().getGlowEffect();
                assertThat(g2).as("glow_effect should not be None after reload").isNotNull();
                assertThat(g2.getRadius()).isEqualTo(15);
            }
        }
    }