[Fact]
    public void ExtGState_FromPage_MultipleStates()
    {
        var pdf = BuildPdfWithMultipleExtGStates();
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var states = ExtGState.FromPage(page);
        Assert.Equal(2, states.Count);
        Assert.Equal(0.5, states["GS1"].FillAlpha);
        Assert.Equal(0.8, states["GS2"].StrokeAlpha);
    }