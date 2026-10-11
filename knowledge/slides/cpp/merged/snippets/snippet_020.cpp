TEST_F(EffectFormatIntegrationTest, Glow) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 100, 100, 200, 200);
    auto& ef = shape.effect_format();
    ef.enable_glow_effect();
    auto* glow = ef.glow_effect();
    ASSERT_NE(glow, nullptr);
    glow->set_radius(15);
    glow->color().set_color(Color::gold);

    auto pres2 = save_and_reopen(pres);
    auto* g2 = pres2.slides()[0].shapes()[0].effect_format().glow_effect();
    ASSERT_NE(g2, nullptr) << "glow_effect should not be None after reload";
    EXPECT_EQ(g2->radius(), 15);
}