[Fact]
    public void MarkedContent_BDC_WithActualText()
    {
        var parser = CreateParser();
        string? actualText = null;

        parser.OnMarkedContentBegin += (_, _) => actualText = parser.State.ActualText;

        var content = Encoding.ASCII.GetBytes("/Span << /ActualText (Hello) >> BDC\nEMC");
        parser.Parse(content);

        Assert.Equal("Hello", actualText);
    }