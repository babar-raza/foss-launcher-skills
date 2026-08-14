TEST(BmpDeviceSmoke, WidthHeightCtor_Roundtrip) {
    Aspose::Pdf::Devices::BmpDevice device(800, 600);
    EXPECT_EQ(device.Width(), 800);
    EXPECT_EQ(device.Height(), 600);
}