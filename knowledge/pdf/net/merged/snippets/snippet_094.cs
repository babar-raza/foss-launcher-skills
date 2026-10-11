[Fact]
    public void Parse_GsOperator_AppliesBlendMode()
    {
        var pdf = BuildPdfWithExtGState("GS1", "<< /Type /ExtGState /BM /Multiply >>");
        using var doc = Document.Open(pdf);
        var page = doc.Pages[1];

        var reader = doc.Reader;
        var parser = new ContentStreamParser(reader);
        var extGStates = ExtGState.ResolveRawFromPage(page.Dict, reader);

        string? capturedBlendMode = null;
        parser.OnOperator += (op, _, state) =>
        {
            if (op == "gs") capturedBlendMode = state.BlendMode;
        };

        var contentBytes = GetContentBytes(page, reader);
        parser.Parse(contentBytes, extGStates: extGStates);

        Assert.Equal("Multiply", capturedBlendMode);
    }