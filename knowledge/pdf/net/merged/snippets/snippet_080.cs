[Fact]
    public void BT_SetsInTextObject()
    {
        var parser = CreateParser();
        bool? duringBt = null;

        parser.OnOperator += (op, _, _) =>
        {
            if (op == "BT") duringBt = parser.State.InTextObject;
        };

        var content = Encoding.ASCII.GetBytes("BT ET");
        parser.Parse(content);

        Assert.True(duringBt);
    }