[Fact]
    public void Page_Rotation_DefaultIsZero()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        Assert.Equal(0, doc.Pages[1].RotateDegrees);
    }