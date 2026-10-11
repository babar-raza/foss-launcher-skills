TEST_F(EffectFormatIntegrationTest, Blur) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 100, 100, 200, 100);
    auto& ef = shape.effect_format();
    ef.set_blur_effect(8, true);

    auto pres2 = save_and_reopen(pres);
    auto* b2 = pres2.slides()[0].shapes()[0].effect_format().blur_effect();
    ASSERT_NE(b2, nullptr) << "blur_effect should not be None after reload";
    EXPECT_EQ(b2->radius(), 8);
}