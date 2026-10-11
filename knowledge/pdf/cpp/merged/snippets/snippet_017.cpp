TEST(AnnotationSaveThroughSmoke, NoAnnotationsLeavesBytesUntouched) {
    // Loading + saving without any Annotations() interaction must
    // hit the fast-path WriteAll branch — saved bytes identical to
    // source bytes.
    const auto src = ReadAll(HelloWorldPdf());

    Document doc{HelloWorldPdf()};
    const std::string out =
        (std::filesystem::temp_directory_path() /
         "aspose_annot_passthrough.pdf").string();
    doc.Save(out);

    const auto saved = ReadAll(out);
    EXPECT_EQ(saved, src);
}