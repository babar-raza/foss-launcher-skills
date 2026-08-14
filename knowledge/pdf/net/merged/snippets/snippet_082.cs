[Fact]
    public void BT_ResetsTextMatricesToIdentity()
    {
        var parser = CreateParser();
        var identity = new double[] { 1, 0, 0, 1, 0, 0 };

        // Set text matrix to something non-identity, then BT should reset
        var content = Encoding.ASCII.GetBytes("BT 2 0 0 2 10 20 Tm ET BT ET");
        parser.Parse(content);

        Assert.Equal(identity, parser.State.TextMatrix);
        Assert.Equal(identity, parser.State.TextLineMatrix);
    }