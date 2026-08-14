TEST_F(TextFormattingIntegrationTest, FontColor) {
    Presentation pres;
    auto [shape, fmt] = shaped(pres);
    fmt->fill_format().set_fill_type(FillType::SOLID);
    fmt->fill_format().solid_fill_color().set_color(Color::red);

    auto pres2 = save_and_reopen(pres);
    auto& fmt2 = reloaded_portion_format(pres2);
    EXPECT_EQ(fmt2.fill_format().fill_type(), FillType::SOLID);
    auto c = fmt2.fill_format().solid_fill_color().color();
    EXPECT_EQ(c.r(), 255);
    EXPECT_EQ(c.g(), 0);
    EXPECT_EQ(c.b(), 0);
}