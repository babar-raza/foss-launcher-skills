[Fact]
    public void AddRedactAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        doc.Pages[1].Annotations.AddRedactAnnotation(
            new Rectangle(100, 700, 300, 720));

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Redact, doc2.Pages[1].Annotations[1].AnnotationType);
    }