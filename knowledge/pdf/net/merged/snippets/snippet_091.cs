[Fact]
    public void ClippingOperators_TrackedViaOnOperator()
    {
        var parser = CreateParser();
        var ops = new List<string>();

        parser.OnOperator += (op, _, _) => ops.Add(op);

        var content = Encoding.ASCII.GetBytes("0 0 100 100 re W n");
        parser.Parse(content);

        Assert.Contains("W", ops);
    }