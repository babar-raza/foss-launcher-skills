TEST(BorderEffectEnum, CanonicalValues) {
    EXPECT_EQ(static_cast<int>(BorderEffect::None),   0);
    EXPECT_EQ(static_cast<int>(BorderEffect::Cloudy), 1);
}