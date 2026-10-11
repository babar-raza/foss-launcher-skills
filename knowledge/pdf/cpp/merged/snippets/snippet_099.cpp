TEST(ColorSmoke, FromArgbHonoursAlpha) {
    auto c = Color::FromArgb(128, 64, 192, 32);
    EXPECT_NEAR(c.A(), 128.0 / 255.0, kEps);
}