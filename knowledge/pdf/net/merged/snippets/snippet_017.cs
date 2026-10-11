[Fact]
    public void CreateGoTo_RoundTrip_PreservesPageIndex()
    {
        var data = PdfBuilder.BuildMultiPage(3);
        using var doc = Document.Open(data);

        var page = doc.Pages[1];
        var action = PdfAction.CreateGoTo(2, "FitH");
        page.Annotations.AddLinkAnnotation(new Rectangle(50, 600, 200, 620), action);

        using var ms = new MemoryStream();
        doc.Save(ms);

        ms.Position = 0;
        using var doc2 = Document.Open(ms.ToArray());
        var annot = doc2.Pages[1].Annotations[1];
        var link = (LinkAnnotation)annot;
        var actionDict = link.InternalReader.ResolveDict(link.Dict.Get("A"));
        Assert.NotNull(actionDict);

        var goToAction = (GoToAction)PdfAction.Create(actionDict!, link.InternalReader);
        Assert.Equal(ActionType.GoTo, goToAction.Type);
        // The page index is stored as integer placeholder in destination array
        Assert.Equal(2, goToAction.DestinationPageIndex);
        Assert.Equal("FitH", goToAction.FitType);
    }