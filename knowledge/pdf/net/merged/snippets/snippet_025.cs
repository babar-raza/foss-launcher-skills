[Fact]
    public void AddFileAttachmentAnnotation_RoundTrip()
    {
        var input = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(input);
        var fileData = "Hello World"u8.ToArray();
        doc.Pages[1].Annotations.AddFileAttachmentAnnotation(
            new Rectangle(100, 700, 120, 720), "See attached", "readme.txt", fileData);

        var saved = doc.ToArray();
        using var doc2 = Document.Open(saved);
        Assert.Single(doc2.Pages[1].Annotations);
        Assert.Equal(AnnotationType.FileAttachment, doc2.Pages[1].Annotations[1].AnnotationType);
    }