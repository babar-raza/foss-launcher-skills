[Fact]
    public void JavaScriptAction_ParsesFromPdf()
    {
        var data = PdfBuilder.BuildWithJavaScriptAction("app.alert('test');");
        using var doc = Document.Open(data);

        var annot = doc.Pages[1].Annotations[1];
        var link = (LinkAnnotation)annot;
        var actionDict = link.InternalReader.ResolveDict(link.Dict.Get("A"));
        Assert.NotNull(actionDict);

        var jsAction = (JavascriptAction)PdfAction.Create(actionDict!, link.InternalReader);
        Assert.Equal(ActionType.JavaScript, jsAction.Type);
        Assert.Equal("app.alert('test');", jsAction.Script);
    }