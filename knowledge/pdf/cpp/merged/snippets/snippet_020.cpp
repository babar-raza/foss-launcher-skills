TEST(AnnotationSelectorSmoke, OneArgCtorAcceptsAnnotation) {
    Ann a;
    Aspose::Pdf::Annotations::AnnotationSelector s{a};
    (void)s;
    SUCCEED();
}