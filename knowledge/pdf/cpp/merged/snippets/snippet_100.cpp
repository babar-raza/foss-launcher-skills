TEST(ColorSmoke, FromArgbThreeArgDefaultsAlpha) {
    auto c = Color::FromArgb(64, 192, 32);
    EXPECT_NEAR(c.A(), 1.0, kEps);
}