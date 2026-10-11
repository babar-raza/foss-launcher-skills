[Fact]
    public void PathPainted_IncludesGraphicsState()
    {
        var parser = CreateParser();
        double? lineWidth = null;

        parser.OnPathPainted += (_, state, __) => lineWidth = state.LineWidth;

        var content = Encoding.ASCII.GetBytes("3.5 w 0 0 m 100 100 l S");
        parser.Parse(content);

        Assert.Equal(3.5, lineWidth);
    }