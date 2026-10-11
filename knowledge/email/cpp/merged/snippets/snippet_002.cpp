int main(int argc, char* argv[])
{
    if (argc < 2)
    {
        std::cerr << "Usage: msg_reader.cpp <path-to-msg> [--out <path>]\n";
        return 1;
    }

    const std::filesystem::path msg_path(argv[1]);
    const auto out_path = read_option(argc, argv, "--out");

    const auto reader = aspose::email::foss::msg::msg_reader::from_file(msg_path);
    const auto document = aspose::email::foss::msg::msg_document::from_reader(reader);
    const auto dump = build_dump(reader, document, msg_path);

    if (!out_path.empty())
    {
        std::ofstream output(out_path, std::ios::binary);
        output << dump;
    }
    else
    {
        std::cout << dump << '\n';
    }

    return 0;
}