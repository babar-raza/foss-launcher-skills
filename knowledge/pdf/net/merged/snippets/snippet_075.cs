[Fact]
    public void ColorSpace_SCN_SetsStrokeColorCMYK()
    {
        var parser = CreateParser();
        // CMYK: C=1, M=0, Y=0, K=0 => R=0, G=1, B=1
        var content = Encoding.ASCII.GetBytes("1 0 0 0 SCN");
        parser.Parse(content);

        Assert.Equal(0.0, parser.State.StrokeR, 3);
        Assert.Equal(1.0, parser.State.StrokeG, 3);
        Assert.Equal(1.0, parser.State.StrokeB, 3);
    }