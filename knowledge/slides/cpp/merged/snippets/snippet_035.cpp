TEST_F(LineFormatIntegrationTest, MultipleDashStyles) {
    std::vector<Aspose::Slides::Foss::LineDashStyle> styles = {
        Aspose::Slides::Foss::LineDashStyle::SOLID,
        Aspose::Slides::Foss::LineDashStyle::DASH,
        Aspose::Slides::Foss::LineDashStyle::DOT,
        Aspose::Slides::Foss::LineDashStyle::DASH_DOT,
    };
    Presentation pres;
    auto& slide = pres.slides()[0];
    for (auto style : styles) {
        auto& shape = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 200, 50);
        shape.line_format().set_dash_style(style);
        EXPECT_EQ(shape.line_format().dash_style(), style);
    }
}