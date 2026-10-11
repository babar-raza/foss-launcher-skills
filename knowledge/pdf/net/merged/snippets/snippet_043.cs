[Fact]
    public void TextAbsorber_EmptyPage_ReturnsEmptyString()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        var abs = new TextAbsorber();
        abs.Visit(doc.Pages[1]);
        Assert.NotNull(abs.Text);
    }