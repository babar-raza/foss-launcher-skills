@Test
    void testEnableDisableEffects() {
        try (var pres = new Presentation()) {
            var shape = pres.getSlides().get(0).getShapes().addAutoShape(ShapeType.RECTANGLE, 100, 100, 200, 100);
            var ef = shape.getEffectFormat();
            ef.enableOuterShadowEffect();
            ef.enableGlowEffect();
            assertThat(ef.isNoEffects()).isFalse();

            ef.disableOuterShadowEffect();
            ef.disableGlowEffect();
            assertThat(ef.isNoEffects()).isTrue();
        }
    }