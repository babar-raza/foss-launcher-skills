[Fact]
    public void AddCaretAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        doc.Pages[1].Annotations.AddCaretAnnotation(
            new Rectangle(100, 700, 110, 710), "insert here");

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Caret, doc2.Pages[1].Annotations[1].AnnotationType);
    }