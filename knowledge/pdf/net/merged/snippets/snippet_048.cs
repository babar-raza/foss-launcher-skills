[Fact]
    public void Page_Fonts_HaveSubtype()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (Subtype test) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        foreach (var font in doc.Pages[1].Fonts)
        {
            Assert.NotNull(font.Subtype);
        }
    }