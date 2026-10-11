[Fact]
    public void NamedAction_ParsesFromPdf()
    {
        var data = PdfBuilder.BuildWithNamedAction("NextPage");
        using var doc = Document.Open(data);

        var annot = doc.Pages[1].Annotations[1];
        Assert.IsType<LinkAnnotation>(annot);

        var link = (LinkAnnotation)annot;
        var actionDict = link.InternalReader.ResolveDict(link.Dict.Get("A"));
        Assert.NotNull(actionDict);

        var namedAction = (NamedAction)PdfAction.Create(actionDict!, link.InternalReader);
        Assert.Equal(ActionType.Named, namedAction.Type);
        Assert.Equal("NextPage", namedAction.Name);
    }