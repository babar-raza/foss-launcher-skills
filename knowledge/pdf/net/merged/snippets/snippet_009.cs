[Fact]
    public void GoToAction_DestinationPageIndex_ResolvesPage0()
    {
        var data = PdfBuilder.BuildWithGoToAction(targetPageIndex: 0, pageCount: 3);
        using var doc = Document.Open(data);

        var annot = doc.Pages[1].Annotations[1];
        var link = (LinkAnnotation)annot;
        var actionDict = link.InternalReader.ResolveDict(link.Dict.Get("A"));
        var goToAction = (GoToAction)PdfAction.Create(actionDict!, link.InternalReader);
        Assert.Equal(0, goToAction.DestinationPageIndex);
    }