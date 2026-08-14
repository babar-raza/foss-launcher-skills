TEST(AnnotationSelectorSmoke, AnnotationAcceptDispatches) {
    Ann a;
    Aspose::Pdf::Annotations::AnnotationSelector s;
    a.Accept(s);
    EXPECT_EQ(a.accept_calls, 1);
    a.Accept(s);
    a.Accept(s);
    EXPECT_EQ(a.accept_calls, 3);
}