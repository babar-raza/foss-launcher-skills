[Fact]
    public void AddSquigglyAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        doc.Pages[1].Annotations.AddSquigglyAnnotation(
            new Rectangle(72, 700, 200, 720));

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Squiggly, doc2.Pages[1].Annotations[1].AnnotationType);
    }