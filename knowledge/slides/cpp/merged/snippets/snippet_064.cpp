TEST_F(SlidesIntegrationTest, CloneSlide) {
    Presentation pres;
    auto& slide = pres.slides()[0];
    slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 100);
    pres.slides().add_clone(slide);
    EXPECT_EQ(pres.slides().size(), 2);
    EXPECT_GE(pres.slides()[1].shapes().size(), 1);
}