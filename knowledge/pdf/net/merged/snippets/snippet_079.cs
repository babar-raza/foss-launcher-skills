[Fact]
    public void DashPattern_SavedAndRestored()
    {
        var parser = CreateParser();
        var content = Encoding.ASCII.GetBytes("[2 4] 1 d q [10] 0 d Q");
        parser.Parse(content);

        Assert.Equal(new double[] { 2, 4 }, parser.State.DashArray);
        Assert.Equal(1.0, parser.State.DashPhase);
    }