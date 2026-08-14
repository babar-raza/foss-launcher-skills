[Fact]
    public void TextAbsorber_ExtractsTextFromPage()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (Hello content) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        var abs = new TextAbsorber();
        abs.Visit(doc.Pages[1]);
        Assert.Contains("Hello content", abs.Text);
    }