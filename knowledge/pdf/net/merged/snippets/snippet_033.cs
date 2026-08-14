[Fact]
    public void Page_WithAnnotations_ParsesCorrectly()
    {
        var data = PdfBuilder.BuildWithAnnotation();
        using var doc = Document.Open(data);
        var annots = doc.Pages[1].Annotations;
        Assert.Single(annots);
        Assert.Equal(AnnotationType.Text, annots[1].AnnotationType);
        Assert.Equal("A note", annots[1].Contents);
    }