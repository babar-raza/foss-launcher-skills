[Fact]
    public void Page_Width_IsPositive()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        Assert.True(doc.Pages[1].Width > 0);
    }