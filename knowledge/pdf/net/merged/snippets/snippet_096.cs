[Fact]
    public void ExtGState_FromPage_ParsesAll()
    {
        var pdf = BuildPdfWithExtGState("GS1", "<< /Type /ExtGState /ca 0.5 /CA 0.7 /BM /Screen >>");
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var states = ExtGState.FromPage(page);
        Assert.True(states.ContainsKey("GS1"));

        var gs = states["GS1"];
        Assert.Equal(0.5, gs.FillAlpha);
        Assert.Equal(0.7, gs.StrokeAlpha);
        Assert.Equal("Screen", gs.BlendMode);
    }