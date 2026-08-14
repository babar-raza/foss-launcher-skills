int main() {
    using namespace Aspose::Pdf::Devices;
    Aspose::Pdf::Document doc(
        (FixtureDir() / "red_rect.pdf").string());

    BmpDevice bmp(Resolution(72));
    std::stringstream sink(
        std::ios::binary | std::ios::out | std::ios::in);
    bmp.Process(doc.Pages()[1], sink);
    const auto bytes = sink.str();

    Check(bytes.size() >= 54u, "Process produced ≥ 54-byte BMP header + body");
    Check(bytes[0] == 'B' && bytes[1] == 'M', "output starts with 'BM'");

    std::uint32_t declared = 0;
    std::memcpy(&declared, bytes.data() + 2, 4);
    Check(declared == bytes.size(),
          "BITMAPFILEHEADER size matches actual byte count");

    std::cout << "\n" << passed << " passed, " << failed << " failed\n";
    return failed == 0 ? 0 : 1;
}