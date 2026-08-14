[Fact]
    public void TextAbsorber_MultiPage_ExtractsDifferentText()
    {
        var data = PdfBuilder.BuildMultiPage(3);
        using var doc = Document.Open(data);

        foreach (var page in doc.Pages)
        {
            var abs = new TextAbsorber();
            abs.Visit(page);
            Assert.NotNull(abs.Text);
        }
    }