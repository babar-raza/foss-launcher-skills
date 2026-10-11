TEST(CharacteristicsSmoke, RotateRoundtrip) {
    Characteristics c;
    EXPECT_EQ(c.Rotate(), Aspose::Pdf::Rotation::None);
    c.Rotate(Aspose::Pdf::Rotation::on180);
    EXPECT_EQ(c.Rotate(), Aspose::Pdf::Rotation::on180);
}