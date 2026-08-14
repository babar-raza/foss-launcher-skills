[Fact]
    public void PathPainted_B_FiresEvent()
    {
        var parser = CreateParser();
        string? capturedOp = null;

        parser.OnPathPainted += (op, _, _) => capturedOp = op;

        var content = Encoding.ASCII.GetBytes("0 0 m 100 0 l 100 100 l h B");
        parser.Parse(content);

        Assert.Equal("B", capturedOp);
    }