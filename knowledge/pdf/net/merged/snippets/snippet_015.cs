[Fact]
    public void CreateNamed_RoundTrip_PreservesName()
    {
        var data = PdfBuilder.BuildMinimal();
        using var doc = Document.Open(data);

        var page = doc.Pages[1];
        var action = PdfAction.CreateNamed("PrevPage");
        page.Annotations.AddLinkAnnotation(new Rectangle(50, 600, 200, 620), action);

        using var ms = new MemoryStream();
        doc.Save(ms);

        ms.Position = 0;
        using var doc2 = Document.Open(ms.ToArray());
        var annot = doc2.Pages[1].Annotations[1];
        var link = (LinkAnnotation)annot;
        var actionDict = link.InternalReader.ResolveDict(link.Dict.Get("A"));
        Assert.NotNull(actionDict);

        var namedAction = (NamedAction)PdfAction.Create(actionDict!, link.InternalReader);
        Assert.Equal("PrevPage", namedAction.Name);
    }