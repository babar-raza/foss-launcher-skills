TEST(BorderSideSmoke, FlagsCombine) {
    EXPECT_EQ(static_cast<int>(BorderSide::All), 15);
    EXPECT_EQ(static_cast<int>(BorderSide::Box), 15);
    const BorderSide lr = BorderSide::Left | BorderSide::Right;
    EXPECT_TRUE(HasSide(lr, BorderSide::Left));
    EXPECT_TRUE(HasSide(lr, BorderSide::Right));
    EXPECT_FALSE(HasSide(lr, BorderSide::Top));
}