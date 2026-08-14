[Fact]
    public void DashPattern_EmptyArray_SolidLine()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("[] 0 d");
        parser.Parse(content);

        Assert.Empty(parser.State.DashArray);
        Assert.Equal(0.0, parser.State.DashPhase);
    }