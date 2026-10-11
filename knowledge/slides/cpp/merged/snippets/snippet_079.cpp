TEST_F(TextFormattingIntegrationTest, Strikethrough) {
    Presentation pres;
    auto [shape, fmt] = shaped(pres);
    fmt->set_strikethrough_type(TextStrikethroughType::SINGLE);

    auto pres2 = save_and_reopen(pres);
    auto& fmt2 = reloaded_portion_format(pres2);
    EXPECT_EQ(fmt2.strikethrough_type(), TextStrikethroughType::SINGLE);
}