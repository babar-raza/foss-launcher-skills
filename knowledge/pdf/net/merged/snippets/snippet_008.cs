[Fact]
    public void GoToAction_DestinationPageIndex_ResolvesFromPageTree()
    {
        // Build a 3-page PDF with a GoTo action targeting page 2 (0-based index 1)
        var data = PdfBuilder.BuildWithGoToAction(targetPageIndex: 1, pageCount: 3);
        using var doc = Document.Open(data);

        var annot = doc.Pages[1].Annotations[1];
        Assert.IsType<LinkAnnotation>(annot);

        var link = (LinkAnnotation)annot;
        var actionDict = link.InternalReader.ResolveDict(link.Dict.Get("A"));
        Assert.NotNull(actionDict);

        var goToAction = (GoToAction)PdfAction.Create(actionDict!, link.InternalReader);
        Assert.Equal(ActionType.GoTo, goToAction.Type);
        Assert.Equal(1, goToAction.DestinationPageIndex);
        Assert.Equal("Fit", goToAction.FitType);
    }