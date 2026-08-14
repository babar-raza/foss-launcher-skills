TEST_F(ShapesIntegrationTest, ShapeFrameProperties) {
    Presentation pres;
    auto& slide = blank_slide(pres);
    auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 200, 200, 300, 250);
    shape.set_rotation(45);

    auto pres2 = save_and_reopen(pres);
    auto& s2 = pres2.slides()[0].shapes()[0];
    EXPECT_EQ(s2.x(), 200);
    EXPECT_EQ(s2.y(), 200);
    EXPECT_EQ(s2.width(), 300);
    EXPECT_EQ(s2.height(), 250);
    EXPECT_EQ(s2.rotation(), 45);
}