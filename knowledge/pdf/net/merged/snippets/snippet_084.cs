[Fact]
    public void PathPainted_f_FiresEvent()
    {
        var parser = CreateParser();
        string? capturedOp = null;

        parser.OnPathPainted += (op, _, _) => capturedOp = op;

        var content = Encoding.ASCII.GetBytes("0 0 100 100 re f");
        parser.Parse(content);

        Assert.Equal("f", capturedOp);
    }