TEST_F(EffectFormatIntegrationTest, SoftEdge) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 100, 100, 200, 100);
    auto& ef = shape.effect_format();
    ef.enable_soft_edge_effect();
    auto* se = ef.soft_edge_effect();
    ASSERT_NE(se, nullptr);
    se->set_radius(10);

    auto pres2 = save_and_reopen(pres);
    auto* se2 = pres2.slides()[0].shapes()[0].effect_format().soft_edge_effect();
    ASSERT_NE(se2, nullptr) << "soft_edge_effect should not be None after reload";
    EXPECT_EQ(se2->radius(), 10);
}