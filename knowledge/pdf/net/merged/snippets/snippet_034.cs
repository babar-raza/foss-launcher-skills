[Fact]
    public void Annotation_Rect_Parsed()
    {
        var data = PdfBuilder.BuildWithAnnotation();
        using var doc = Document.Open(data);
        var annot = doc.Pages[1].Annotations[1];
        Assert.NotNull(annot.Rect);
        Assert.Equal(100, annot.Rect!.LLX);
    }