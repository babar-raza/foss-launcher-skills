[Fact]
    public void Parse_GsOperator_SaveRestore_Preserves()
    {
        // Content: q /GS1 gs Q — opacity should be restored after Q
        var pdf = BuildPdfWithExtGStateContent("GS1", "<< /Type /ExtGState /ca 0.2 >>",
            "q /GS1 gs Q");
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var reader = doc.Reader;
        var parser = new ContentStreamParser(reader);
        var extGStates = ExtGState.ResolveRawFromPage(page.Dict, reader);

        double lastFillAlpha = -1;
        parser.OnOperator += (op, _, state) =>
        {
            lastFillAlpha = state.FillAlpha;
        };

        var contentBytes = GetContentBytes(page, reader);
        parser.Parse(contentBytes, extGStates: extGStates);

        // After Q restore, fill alpha should be back to 1.0
        Assert.Equal(1.0, lastFillAlpha);
    }