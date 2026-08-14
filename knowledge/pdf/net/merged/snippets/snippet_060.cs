[Fact]
    public void TextFragment_HasTextProperty()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (Fragment text) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        var absorber = new TextFragmentAbsorber();
        absorber.Visit(doc.Pages[1]);
        foreach (var fragment in absorber.TextFragments)
        {
            Assert.NotNull(fragment.Text);
            Assert.NotEmpty(fragment.Text);
        }
    }