TEST(AnnotationSaveThroughSmoke, MultipleAnnotationsAllPersist) {
    Document doc{HelloWorldPdf()};
    TextAnnotation a{doc};
    a.Rect(Rectangle{10.0, 10.0, 50.0, 30.0, false});
    a.Contents("first");
    TextAnnotation b{doc};
    b.Rect(Rectangle{60.0, 60.0, 90.0, 80.0, false});
    b.Contents("second");

    doc.Pages()[1].Annotations().Add(a);
    doc.Pages()[1].Annotations().Add(b);

    const std::string out =
        (std::filesystem::temp_directory_path() /
         "aspose_annot_multi.pdf").string();
    doc.Save(out);

    const auto saved = ReadAll(out);
    const auto dump = foundation::objects::Parse(
        std::span<const std::byte>(saved.data(), saved.size()));

    // Count /Annot objects (Type=Annot Subtype=Text).
    int annot_count = 0;
    for (const auto& obj : dump.objects) {
        const auto* d = std::get_if<foundation::objects::Dict>(
            &obj.value.v);
        if (d == nullptr) continue;
        bool is_annot = false, is_text = false;
        for (const auto& kv : d->entries) {
            if (kv.first == "Type") {
                if (auto* s = std::get_if<std::string>(&kv.second.v);
                        s && *s == "Annot") is_annot = true;
            } else if (kv.first == "Subtype") {
                if (auto* s = std::get_if<std::string>(&kv.second.v);
                        s && *s == "Text") is_text = true;
            }
        }
        if (is_annot && is_text) ++annot_count;
    }
    // Note: parse may surface duplicate object ids across the
    // incremental xref section (original + appended). The
    // incremental-section's two Text-annot entries are the new
    // additions; original bytes carry none.
    EXPECT_EQ(annot_count, 2);
}