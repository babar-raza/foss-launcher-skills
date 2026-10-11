TEST_F(ThreeDFormatIntegrationTest, LightRig) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 100, 100, 200, 100);
    auto& lr = shape.three_d_format().light_rig();
    lr.set_light_type(LightRigPresetType::BALANCED);
    lr.set_direction(LightingDirection::TOP);

    auto pres2 = save_and_reopen(pres);
    auto& lr2 = pres2.slides()[0].shapes()[0].three_d_format().light_rig();
    EXPECT_EQ(lr2.light_type(), LightRigPresetType::BALANCED);
    EXPECT_EQ(lr2.direction(), LightingDirection::TOP);
}