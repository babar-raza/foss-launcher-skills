TEST(AnnotationSelectorSmoke, AnnotationCollectionAcceptIterates) {
    Ann a1, a2, a3;
    Aspose::Pdf::Annotations::AnnotationCollection coll;
    coll.Add(a1);
    coll.Add(a2);
    coll.Add(a3);

    Aspose::Pdf::Annotations::AnnotationSelector s;
    coll.Accept(s);

    EXPECT_EQ(a1.accept_calls, 1);
    EXPECT_EQ(a2.accept_calls, 1);
    EXPECT_EQ(a3.accept_calls, 1);
}