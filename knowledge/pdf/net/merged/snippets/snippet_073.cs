[Fact]
    public void ColorSpace_SC_SetsStrokeColorRGB()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("0.1 0.3 0.5 SC");
        parser.Parse(content);

        Assert.Equal(0.1, parser.State.StrokeR, 3);
        Assert.Equal(0.3, parser.State.StrokeG, 3);
        Assert.Equal(0.5, parser.State.StrokeB, 3);
    }