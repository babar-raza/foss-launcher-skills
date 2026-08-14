[Fact]
    public void Page_Images_WithImagePdf_HasImages()
    {
        var data = PdfBuilder.BuildWithUncompressedImage(4, 4);
        using var doc = Document.Open(data);

        var images = doc.Pages[1].Images;
        Assert.True(images.Count > 0);
    }