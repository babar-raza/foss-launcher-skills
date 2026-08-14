[Fact]
    public void CreateUri_RoundTrip_PreservesUri()
    {
        // Build a PDF with a URI action, save, reload, verify
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        var page = doc.Pages[1];
        var action = PdfAction.CreateUri("https://aspose.com/test");
        page.Annotations.AddLinkAnnotation(new Rectangle(50, 700, 200, 720), action);

        using var ms = new MemoryStream();
        doc.Save(ms);

        ms.Position = 0;
        using var doc2 = Document.Open(ms.ToArray());
        var annot = doc2.Pages[1].Annotations[1];
        Assert.IsType<LinkAnnotation>(annot);
        var link = (LinkAnnotation)annot;
        Assert.Equal("https://aspose.com/test", link.Uri);
    }