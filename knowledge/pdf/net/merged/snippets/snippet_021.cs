[Fact]
    public void AddInkAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        var page = doc.Pages[1];

        var paths = new[] { new double[] { 100, 200, 150, 250, 200, 200 } };
        page.Annotations.AddInkAnnotation(
            new Rectangle(100, 200, 200, 250), paths);

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Ink, doc2.Pages[1].Annotations[1].AnnotationType);
    }