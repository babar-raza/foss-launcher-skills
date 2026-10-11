[Fact]
    public void CurveTo_v_y_TrackedViaOnOperator()
    {
        var parser = CreateParser();
        var ops = new List<string>();

        parser.OnOperator += (op, _, _) => ops.Add(op);

        var content = Encoding.ASCII.GetBytes("10 20 30 40 v 50 60 70 80 y");
        parser.Parse(content);

        Assert.Contains("v", ops);
        Assert.Contains("y", ops);
    }