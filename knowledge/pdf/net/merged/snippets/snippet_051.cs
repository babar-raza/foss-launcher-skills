[Fact]
    public void Page_Height_IsPositive()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        Assert.True(doc.Pages[1].Height > 0);
    }