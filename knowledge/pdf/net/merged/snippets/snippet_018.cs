[Fact]
    public void AnnotationCollection_AddLinkWithAction_CreatesLinkAnnotation()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        var page = doc.Pages[1];
        Assert.Empty(page.Annotations);

        var action = PdfAction.CreateUri("https://example.org");
        var annot = page.Annotations.AddLinkAnnotation(new Rectangle(10, 10, 100, 30), action);

        Assert.Single(page.Annotations);
        Assert.Equal(AnnotationType.Link, annot.AnnotationType);
    }