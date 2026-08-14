[Fact]
    public void TextFragment_HasFontSize()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 14 Tf (Sized text) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        var absorber = new TextFragmentAbsorber();
        absorber.Visit(doc.Pages[1]);
        foreach (var fragment in absorber.TextFragments)
        {
            Assert.True(fragment.FontSize > 0);
        }
    }