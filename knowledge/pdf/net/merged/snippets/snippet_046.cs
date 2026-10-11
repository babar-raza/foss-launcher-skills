[Fact]
    public void Page_Fonts_AreEnumerable()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (Enum fonts) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        var fonts = doc.Pages[1].Fonts;
        var n = 0;
        foreach (var _ in fonts) n++;
        Assert.Equal(fonts.Count, n);
    }