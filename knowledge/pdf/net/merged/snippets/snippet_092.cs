[Fact]
    public void Parse_GsOperator_AppliesFillOpacity()
    {
        // Build a PDF with ExtGState that sets fill opacity
        var pdf = BuildPdfWithExtGState("GS1", "<< /Type /ExtGState /ca 0.5 >>");
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var reader = doc.Reader;
        var parser = new ContentStreamParser(reader);
        var extGStates = ExtGState.ResolveRawFromPage(page.Dict, reader);

        double? capturedFillAlpha = null;
        parser.OnOperator += (op, _, state) =>
        {
            if (op == "gs") capturedFillAlpha = state.FillAlpha;
        };

        var contentBytes = GetContentBytes(page, reader);
        parser.Parse(contentBytes, extGStates: extGStates);

        Assert.Equal(0.5, capturedFillAlpha);
    }