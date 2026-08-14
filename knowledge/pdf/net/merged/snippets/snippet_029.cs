[Fact]
    public void AddPopupAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        doc.Pages[1].Annotations.AddPopupAnnotation(
            new Rectangle(200, 600, 400, 700), open: true);

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.Popup, doc2.Pages[1].Annotations[1].AnnotationType);
    }