[Fact]
    public void Page_Rotation_ReadsRotation()
    {
        var data = PdfBuilder.BuildWithRotation(90);
        using var doc = Document.Open(data);

        Assert.Equal(90, doc.Pages[1].RotateDegrees);
    }