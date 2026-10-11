TEST(AnnotationSmoke, PropertyRoundtrip) {
    Ann a;
    a.Flags(AnnotationFlags::Print | AnnotationFlags::ReadOnly);
    a.UpdateAppearanceOnConvert(true);
    a.UseFontSubset(true);
    a.Contents("hello");
    a.Name("note1");
    a.ActiveState("On");
    a.Color(Color::Red());
    a.Alignment(TextAlignment::Right);
    a.HorizontalAlignment(Aspose::Pdf::HorizontalAlignment::Center);

    EXPECT_EQ(static_cast<int>(a.Flags()),
              static_cast<int>(AnnotationFlags::Print
                  | AnnotationFlags::ReadOnly));
    EXPECT_TRUE(a.UpdateAppearanceOnConvert());
    EXPECT_TRUE(a.UseFontSubset());
    EXPECT_EQ(a.Contents(), "hello");
    EXPECT_EQ(a.Name(), "note1");
    EXPECT_EQ(a.ActiveState(), "On");
    EXPECT_EQ(a.Alignment(), TextAlignment::Right);
    EXPECT_EQ(a.HorizontalAlignment(),
              Aspose::Pdf::HorizontalAlignment::Center);
}