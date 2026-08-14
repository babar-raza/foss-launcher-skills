[Fact]
    public void LaunchAction_ParsesFromPdf()
    {
        var data = PdfBuilder.BuildWithLaunchAction("readme.txt");
        using var doc = Document.Open(data);

        var annot = doc.Pages[1].Annotations[1];
        var link = (LinkAnnotation)annot;
        var actionDict = link.InternalReader.ResolveDict(link.Dict.Get("A"));
        Assert.NotNull(actionDict);

        var launchAction = (LaunchAction)PdfAction.Create(actionDict!, link.InternalReader);
        Assert.Equal(ActionType.Launch, launchAction.Type);
        Assert.Equal("readme.txt", launchAction.File);
    }