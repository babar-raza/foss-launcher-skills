TEST_F(EffectFormatIntegrationTest, EnableDisableEffects) {
    Presentation pres;
    auto& shape = pres.slides()[0].shapes().add_auto_shape(
        ShapeType::RECTANGLE, 100, 100, 200, 100);
    auto& ef = shape.effect_format();
    ef.enable_outer_shadow_effect();
    ef.enable_glow_effect();
    EXPECT_FALSE(ef.is_no_effects());

    ef.disable_outer_shadow_effect();
    ef.disable_glow_effect();
    EXPECT_TRUE(ef.is_no_effects());
}