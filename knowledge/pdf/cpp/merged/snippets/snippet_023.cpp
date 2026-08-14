TEST(AnnotationSelectorSmoke, EmptyCollectionAcceptIsNoop) {
    Aspose::Pdf::Annotations::AnnotationCollection coll;
    Aspose::Pdf::Annotations::AnnotationSelector s;
    coll.Accept(s);  // should not throw
    SUCCEED();
}