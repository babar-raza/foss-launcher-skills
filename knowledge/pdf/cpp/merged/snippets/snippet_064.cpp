TEST(BmpDeviceSmoke, PageSizeAndResolution_Roundtrip) {
    Aspose::Pdf::Devices::Resolution res(150);
    Aspose::Pdf::Devices::BmpDevice device(
        Aspose::Pdf::PageSize::A5(), res);
    // Canonical Aspose.PDF 26.4.0 A5 = 421 × 595.
    EXPECT_EQ(device.Width(), 421);
    EXPECT_EQ(device.Height(), 595);
    EXPECT_EQ(device.Resolution().X(), 150);
}