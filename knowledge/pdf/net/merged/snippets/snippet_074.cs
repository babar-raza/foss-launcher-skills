[Fact]
    public void ColorSpace_scn_SetsFillColorGray()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("0.75 scn");
        parser.Parse(content);

        Assert.Equal(0.75, parser.State.FillR, 3);
        Assert.Equal(0.75, parser.State.FillG, 3);
        Assert.Equal(0.75, parser.State.FillB, 3);
    }