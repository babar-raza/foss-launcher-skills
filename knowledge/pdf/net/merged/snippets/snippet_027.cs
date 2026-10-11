[Fact]
    public void AddPolygonAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        var vertices = new double[] { 100, 200, 200, 300, 150, 350 };
        doc.Pages[1].Annotations.AddPolygonAnnotation(
            new Rectangle(100, 200, 200, 350), vertices);

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Polygon, doc2.Pages[1].Annotations[1].AnnotationType);
    }