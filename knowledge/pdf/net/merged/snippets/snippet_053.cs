[Fact]
    public void Page_Images_TextOnlyPdf_HasNoImages()
    {
        var content = Encoding.ASCII.GetBytes("BT /F1 12 Tf (No images) Tj ET");
        var data = PdfBuilder.BuildWithTextContent(content);
        using var doc = Document.Open(data);

        Assert.True(doc.Pages[1].Images.Count == 0);
    }