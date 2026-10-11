TEST_F(TextFormattingIntegrationTest, BoldItalic) {
    Presentation pres;
    auto [shape, fmt] = shaped(pres);
    fmt->set_font_bold(NullableBool::TRUE);
    fmt->set_font_italic(NullableBool::TRUE);

    auto pres2 = save_and_reopen(pres);
    auto& fmt2 = reloaded_portion_format(pres2);
    EXPECT_EQ(fmt2.font_bold(), NullableBool::TRUE);
    EXPECT_EQ(fmt2.font_italic(), NullableBool::TRUE);
}