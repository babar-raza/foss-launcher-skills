TEST(BmpDeviceSmoke, ResolutionCtor_Roundtrip) {
    Aspose::Pdf::Devices::Resolution res(96);
    Aspose::Pdf::Devices::BmpDevice device(res);
    EXPECT_EQ(device.Resolution().X(), 96);
}