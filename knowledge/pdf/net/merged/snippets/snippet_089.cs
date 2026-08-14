[Fact]
    public void PathOperators_TrackedViaOnOperator()
    {
        var parser = CreateParser();
        var ops = new List<string>();

        parser.OnOperator += (op, _, _) => ops.Add(op);

        var content = Encoding.ASCII.GetBytes("10 20 m 30 40 l 50 60 70 80 90 100 c h 0 0 100 50 re");
        parser.Parse(content);

        Assert.Contains("m", ops);
        Assert.Contains("l", ops);
        Assert.Contains("c", ops);
        Assert.Contains("h", ops);
        Assert.Contains("re", ops);
    }