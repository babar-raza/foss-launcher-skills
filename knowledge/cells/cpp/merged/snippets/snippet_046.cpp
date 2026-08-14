std::filesystem::path TestOutputRoot()
{
#ifdef ASPOSE_CELLS_FOSS_TEST_OUTPUT_DIR
    auto root = std::filesystem::path(ASPOSE_CELLS_FOSS_TEST_OUTPUT_DIR);
#else
    auto root = std::filesystem::path("workspace") / "temp";
#endif
    if (root.is_relative()) {
        root = std::filesystem::current_path() / root;
    }
    std::filesystem::create_directories(root);
    return root;
}