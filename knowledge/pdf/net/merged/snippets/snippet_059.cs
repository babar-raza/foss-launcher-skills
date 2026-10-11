[Fact]
    public void TextFragmentAbsorber_EmptyPage_NoFragments()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        var absorber = new TextFragmentAbsorber();
        absorber.Visit(doc.Pages[1]);
        Assert.True(absorber.TextFragments.Count == 0);
    }