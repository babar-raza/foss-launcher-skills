[Fact]
    public void DashPattern_d_SetsArrayAndPhase()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("[3 5] 6 d");
        parser.Parse(content);

        Assert.Equal(new double[] { 3, 5 }, parser.State.DashArray);
        Assert.Equal(6.0, parser.State.DashPhase);
    }