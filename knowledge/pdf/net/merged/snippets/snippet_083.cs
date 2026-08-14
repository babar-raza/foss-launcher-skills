[Fact]
    public void PathPainted_S_FiresEvent()
    {
        var parser = CreateParser();
        string? capturedOp = null;

        parser.OnPathPainted += (op, _, _) => capturedOp = op;

        var content = Encoding.ASCII.GetBytes("100 200 m 300 400 l S");
        parser.Parse(content);

        Assert.Equal("S", capturedOp);
    }