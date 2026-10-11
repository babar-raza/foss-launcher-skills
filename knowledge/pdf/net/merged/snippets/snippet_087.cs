[Fact]
    public void PathPainted_AllPaintingOperators_Fire()
    {
        var parser = CreateParser();
        var ops = new List<string>();

        parser.OnPathPainted += (op, _, _) => ops.Add(op);

        var content = Encoding.ASCII.GetBytes(
            "0 0 m S 0 0 m s 0 0 m f 0 0 m F " +
            "0 0 m f* 0 0 m B 0 0 m B* " +
            "0 0 m b 0 0 m b* 0 0 m n");
        parser.Parse(content);

        Assert.Equal(new[] { "S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n" }, ops);
    }