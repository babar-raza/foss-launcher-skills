[Fact]
    public void Page_Fonts_HaveBaseFont()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (Base font) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        foreach (var font in doc.Pages[1].Fonts)
        {
            Assert.NotNull(font.BaseFont);
        }
    }