TEST(ActionsSmoke, ClonesThroughLinkAnnotationAction) {
    Document doc;
    Page page = doc.Pages().Add();
    LinkAnnotation link{page, Rectangle{0.0, 0.0, 100.0, 20.0, false}};

    // Each action type survives the clone done by LinkAnnotation::Action.
    link.Action(NamedAction{PredefinedAction::LastPage});
    ASSERT_NE(link.Action(), nullptr);
    EXPECT_EQ(link.Action()->ToString(), "LastPage");
    EXPECT_NE(dynamic_cast<NamedAction*>(link.Action()), nullptr);

    link.Action(JavascriptAction{"this.print();"});
    EXPECT_EQ(link.Action()->GetECMAScriptString(), "this.print();");
    EXPECT_NE(dynamic_cast<JavascriptAction*>(link.Action()), nullptr);

    SubmitFormAction sf;
    sf.Url(FileSpecification{"https://example.org/x"});
    link.Action(sf);
    auto* got = dynamic_cast<SubmitFormAction*>(link.Action());
    ASSERT_NE(got, nullptr);
    EXPECT_EQ(got->Url().Name(), "https://example.org/x");
}