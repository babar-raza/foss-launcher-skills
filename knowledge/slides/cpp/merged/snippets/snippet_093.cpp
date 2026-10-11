TEST_F(ThreeDFormatIntegrationTest, Camera) {
    Presentation pres;
    auto& slide = clear_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 100, 100, 200, 100);
    shape.three_d_format().camera().set_camera_type(CameraPresetType::PERSPECTIVE_ABOVE);

    auto pres2 = save_and_reopen(pres);
    auto& cam = pres2.slides()[0].shapes()[0].three_d_format().camera();
    EXPECT_EQ(cam.camera_type(), CameraPresetType::PERSPECTIVE_ABOVE);
}