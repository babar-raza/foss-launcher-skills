TEST_F(DocumentPropertiesIntegrationTest, CorePropertiesPersist) {
    Presentation pres;
    auto& props = pres.document_properties();
    props.set_title("My Presentation");
    props.set_subject("Demo Subject");
    props.set_author("John Doe");
    props.set_keywords("demo, test");
    props.set_category("Examples");

    auto pres2 = save_and_reopen(pres);
    auto& p2 = pres2.document_properties();
    EXPECT_EQ(p2.title(), "My Presentation");
    EXPECT_EQ(p2.subject(), "Demo Subject");
    EXPECT_EQ(p2.author(), "John Doe");
    EXPECT_EQ(p2.keywords(), "demo, test");
    EXPECT_EQ(p2.category(), "Examples");
}