[Fact]
    public void AddStampAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        doc.Pages[1].Annotations.AddStampAnnotation(
            new Rectangle(100, 700, 200, 750), "Approved!", "Approved");

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Stamp, doc2.Pages[1].Annotations[1].AnnotationType);
        Assert.Equal("Approved!", doc2.Pages[1].Annotations[1].Contents);
    }