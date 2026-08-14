TEST(BorderSmoke, AccessorRoundtrip) {
    Border b{nullptr};
    EXPECT_EQ(b.Width(), 1);
    EXPECT_EQ(b.Style(), BorderStyle::Solid);
    EXPECT_EQ(b.Effect(), BorderEffect::None);

    b.Width(3);
    b.HCornerRadius(5.0);
    b.VCornerRadius(7.0);
    b.EffectIntensity(2);
    b.Style(BorderStyle::Dashed);
    b.Effect(BorderEffect::Cloudy);

    EXPECT_EQ(b.Width(), 3);
    EXPECT_NEAR(b.HCornerRadius(), 5.0, kEps);
    EXPECT_NEAR(b.VCornerRadius(), 7.0, kEps);
    EXPECT_EQ(b.EffectIntensity(), 2);
    EXPECT_EQ(b.Style(), BorderStyle::Dashed);
    EXPECT_EQ(b.Effect(), BorderEffect::Cloudy);
}