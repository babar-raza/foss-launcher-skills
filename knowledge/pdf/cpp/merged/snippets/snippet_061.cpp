TEST(BmpDeviceSmoke, DefaultCtor) {
    Aspose::Pdf::Devices::BmpDevice device;
    EXPECT_EQ(device.Width(), 0);
}