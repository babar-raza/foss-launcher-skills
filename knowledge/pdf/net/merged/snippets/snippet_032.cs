[Fact]
    public void Page_WithNoAnnotations_ReturnsEmptyCollection()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);
        Assert.Empty(doc.Pages[1].Annotations);
    }