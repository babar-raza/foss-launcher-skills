TEST(DocumentPropertiesIntegrationTestNoFixture, RemoveCustomProperty) {
    Presentation pres;
    auto& props = pres.document_properties();
    props.set_custom_property_value("A", std::any(std::string("val")));
    props.set_custom_property_value("B", std::any(std::string("val")));
    EXPECT_EQ(props.count_of_custom_properties(), 2);

    props.remove_custom_property("A");
    EXPECT_EQ(props.count_of_custom_properties(), 1);
    EXPECT_FALSE(props.contains_custom_property("A"));
    EXPECT_TRUE(props.contains_custom_property("B"));
}