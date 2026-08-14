[Fact]
    public void Parse_GsOperator_AppliesStrokeOpacity()
    {
        var pdf = BuildPdfWithExtGState("GS1", "<< /Type /ExtGState /CA 0.3 >>");
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var reader = doc.Reader;
        var parser = new ContentStreamParser(reader);
        var extGStates = ExtGState.ResolveRawFromPage(page.Dict, reader);

        double? capturedStrokeAlpha = null;
        parser.OnOperator += (op, _, state) =>
        {
            if (op == "gs") capturedStrokeAlpha = state.StrokeAlpha;
        };

        var contentBytes = GetContentBytes(page, reader);
        parser.Parse(contentBytes, extGStates: extGStates);

        Assert.Equal(0.3, capturedStrokeAlpha);
    }