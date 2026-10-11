[Fact]
    public void Page_Fonts_HasCount()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (Font test) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        var fonts = doc.Pages[1].Fonts;
        Assert.NotNull(fonts);
        Assert.True(fonts.Count > 0);
    }