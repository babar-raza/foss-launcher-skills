[Fact]
    public void TextFragmentAbsorber_NoMatch_ReturnsZero()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (Hello World) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        var absorber = new TextFragmentAbsorber("ZZZZZ");
        absorber.Visit(doc.Pages[1]);
        Assert.True(absorber.TextFragments.Count == 0);
    }