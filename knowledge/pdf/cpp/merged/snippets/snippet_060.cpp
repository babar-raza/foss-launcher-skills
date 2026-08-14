TEST(BmpDeviceE2E, RedRect_ProducesValidBmp) {
    const auto pdf = FixtureRoot() / "red_rect.pdf";
    Aspose::Pdf::Document doc(pdf.string());
    auto page = doc.Pages()[1];

    Aspose::Pdf::Devices::BmpDevice bmp(Aspose::Pdf::Devices::Resolution(72));
    std::stringstream sink(std::ios::binary | std::ios::out | std::ios::in);
    bmp.Process(page, sink);

    const std::string out = sink.str();
    ASSERT_GE(out.size(), 54u) << "BMP24 must be ≥ 14 + 40 byte header";

    // BITMAPFILEHEADER signature "BM".
    EXPECT_EQ(out[0], 'B');
    EXPECT_EQ(out[1], 'M');

    // File size at offset 2 must equal actual buffer size.
    std::uint32_t declared = 0;
    std::memcpy(&declared, out.data() + 2, 4);
    EXPECT_EQ(declared, out.size());

    // Pixel-data offset at byte 10 = 14 (file hdr) + 40 (info hdr) = 54.
    std::uint32_t pixel_offset = 0;
    std::memcpy(&pixel_offset, out.data() + 10, 4);
    EXPECT_EQ(pixel_offset, 54u);
}