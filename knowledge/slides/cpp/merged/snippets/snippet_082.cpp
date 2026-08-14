TEST_F(TextFormattingIntegrationTest, LatinFont) {
    Presentation pres;
    auto [shape, fmt] = shaped(pres);
    fmt->set_latin_font(FontData("Courier New"));

    auto pres2 = save_and_reopen(pres);
    auto& fmt2 = reloaded_portion_format(pres2);
    ASSERT_TRUE(fmt2.latin_font().has_value());
    EXPECT_EQ(fmt2.latin_font()->font_name(), "Courier New");
}