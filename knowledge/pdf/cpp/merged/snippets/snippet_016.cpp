TEST(AnnotationSaveThroughSmoke, TextAnnotationPersistsAndReopens) {
    // 1. Load a 1-page PDF + add a TextAnnotation through the
    //    Page.Annotations() accessor.
    Document doc{HelloWorldPdf()};
    TextAnnotation a{doc};
    a.Rect(Rectangle{100.0, 700.0, 200.0, 720.0, false});
    a.Contents("Cluster save-through proof");

    doc.Pages()[1].Annotations().Add(a);

    // 2. Save to /tmp and re-read raw bytes.
    const std::string out =
        (std::filesystem::temp_directory_path() /
         "aspose_annot_save_through.pdf").string();
    doc.Save(out);

    const auto saved = ReadAll(out);

    // 3. Walk the saved doc's indirect objects, find the /Page +
    //    its /Annots entry, and the referenced /Annot dict.
    const auto dump = foundation::objects::Parse(
        std::span<const std::byte>(saved.data(), saved.size()));

    // Find the Page object.
    const foundation::objects::IndirectObject* page = nullptr;
    for (const auto& obj : dump.objects) {
        const auto* d = std::get_if<foundation::objects::Dict>(
            &obj.value.v);
        if (d == nullptr) continue;
        for (const auto& kv : d->entries) {
            if (kv.first == "Type") {
                if (auto* s = std::get_if<std::string>(&kv.second.v);
                        s && *s == "Page") {
                    page = &obj;
                }
            }
        }
        if (page) break;
    }
    ASSERT_NE(page, nullptr);

    // Find /Annots on the page.
    const auto& page_dict = std::get<foundation::objects::Dict>(
        page->value.v);
    const foundation::objects::Array* annots = nullptr;
    for (const auto& kv : page_dict.entries) {
        if (kv.first == "Annots") {
            annots = std::get_if<foundation::objects::Array>(
                &kv.second.v);
        }
    }
    ASSERT_NE(annots, nullptr);
    ASSERT_EQ(annots->items.size(), 1u);
    const auto* ref = std::get_if<foundation::objects::Ref>(
        &annots->items[0].v);
    ASSERT_NE(ref, nullptr);

    // Resolve the Ref to the actual /Annot dict.
    const foundation::objects::IndirectObject* annot_obj = nullptr;
    for (const auto& obj : dump.objects) {
        if (obj.id == ref->id) annot_obj = &obj;
    }
    ASSERT_NE(annot_obj, nullptr);
    const auto* annot_dict = std::get_if<foundation::objects::Dict>(
        &annot_obj->value.v);
    ASSERT_NE(annot_dict, nullptr);

    // Verify the v1 baseline entries.
    std::string type, subtype, contents;
    const foundation::objects::Array* rect = nullptr;
    foundation::objects::Ref parent_ref{};
    for (const auto& kv : annot_dict->entries) {
        if (kv.first == "Type") {
            if (auto* s = std::get_if<std::string>(&kv.second.v); s) type = *s;
        } else if (kv.first == "Subtype") {
            if (auto* s = std::get_if<std::string>(&kv.second.v); s) subtype = *s;
        } else if (kv.first == "Rect") {
            rect = std::get_if<foundation::objects::Array>(&kv.second.v);
        } else if (kv.first == "Contents") {
            if (auto* s = std::get_if<foundation::objects::String>(&kv.second.v);
                    s) {
                contents.assign(
                    reinterpret_cast<const char*>(s->bytes.data()),
                    s->bytes.size());
            }
        } else if (kv.first == "P") {
            if (auto* r = std::get_if<foundation::objects::Ref>(&kv.second.v);
                    r) parent_ref = *r;
        }
    }

    EXPECT_EQ(type, "Annot");
    EXPECT_EQ(subtype, "Text");
    EXPECT_EQ(contents, "Cluster save-through proof");
    EXPECT_EQ(parent_ref.id, page->id);
    ASSERT_NE(rect, nullptr);
    ASSERT_EQ(rect->items.size(), 4u);
    EXPECT_DOUBLE_EQ(std::get<double>(rect->items[0].v), 100.0);
    EXPECT_DOUBLE_EQ(std::get<double>(rect->items[1].v), 700.0);
    EXPECT_DOUBLE_EQ(std::get<double>(rect->items[2].v), 200.0);
    EXPECT_DOUBLE_EQ(std::get<double>(rect->items[3].v), 720.0);
}