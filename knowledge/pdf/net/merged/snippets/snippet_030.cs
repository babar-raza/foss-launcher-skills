[Fact]
    public void AddWatermarkAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        doc.Pages[1].Annotations.AddWatermarkAnnotation(
            new Rectangle(0, 0, 612, 792), "CONFIDENTIAL");

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Watermark, doc2.Pages[1].Annotations[1].AnnotationType);
        Assert.Equal("CONFIDENTIAL", doc2.Pages[1].Annotations[1].Contents);
    }