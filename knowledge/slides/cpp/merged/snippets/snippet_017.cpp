TEST_F(DocumentPropertiesIntegrationTest, CustomIntPropertyPersists) {
    Presentation pres;
    pres.document_properties().set_custom_property_value(
        "Count", std::any(static_cast<int32_t>(42)));

    auto pres2 = save_and_reopen(pres);
    std::any out;
    bool found = pres2.document_properties().get_custom_property_value("Count", out);
    ASSERT_TRUE(found);
    ASSERT_TRUE(out.has_value());
    EXPECT_EQ(std::any_cast<int32_t>(out), 42);
}