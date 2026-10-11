[Fact]
    public void Page_MediaBox_HasDimensions()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        var mb = doc.Pages[1].MediaBox;
        Assert.True(mb.Width > 0);
        Assert.True(mb.Height > 0);
    }