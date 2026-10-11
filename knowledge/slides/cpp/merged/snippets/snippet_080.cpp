TEST_F(TextFormattingIntegrationTest, FontSize) {
    Presentation pres;
    auto [shape, fmt] = shaped(pres);
    fmt->set_font_height(28);

    auto pres2 = save_and_reopen(pres);
    auto& fmt2 = reloaded_portion_format(pres2);
    EXPECT_EQ(fmt2.font_height(), 28);
}