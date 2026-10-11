TEST_F(EffectFormatIntegrationTest, OuterShadow) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 100, 100, 200, 100);
    auto& ef = shape.effect_format();
    ef.enable_outer_shadow_effect();
    auto* shadow = ef.outer_shadow_effect();
    ASSERT_NE(shadow, nullptr);
    shadow->set_blur_radius(10);
    shadow->set_direction(315);
    shadow->set_distance(8);
    shadow->shadow_color().set_color(Color::from_argb(128, 0, 0, 0));

    auto pres2 = save_and_reopen(pres);
    auto& ef2 = pres2.slides()[0].shapes()[0].effect_format();
    auto* s2 = ef2.outer_shadow_effect();
    ASSERT_NE(s2, nullptr) << "outer_shadow_effect should not be None after reload";
    EXPECT_EQ(s2->blur_radius(), 10);
    EXPECT_EQ(s2->direction(), 315);
    EXPECT_EQ(s2->distance(), 8);
}