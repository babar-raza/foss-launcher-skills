[Fact]
    public void ColorSpace_sc_SetsFillColorRGB()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("0.2 0.4 0.6 sc");
        parser.Parse(content);

        Assert.Equal(0.2, parser.State.FillR, 3);
        Assert.Equal(0.4, parser.State.FillG, 3);
        Assert.Equal(0.6, parser.State.FillB, 3);
    }