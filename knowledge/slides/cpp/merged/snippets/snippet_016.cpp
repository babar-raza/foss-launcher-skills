TEST_F(DocumentPropertiesIntegrationTest, CustomStringPropertyPersists) {
    Presentation pres;
    pres.document_properties().set_custom_property_value(
        "MyProp", std::any(std::string("hello")));

    auto pres2 = save_and_reopen(pres);
    std::any out;
    bool found = pres2.document_properties().get_custom_property_value("MyProp", out);
    ASSERT_TRUE(found);
    ASSERT_TRUE(out.has_value());
    EXPECT_EQ(std::any_cast<std::string>(out), "hello");
}