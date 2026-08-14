[Fact]
    public void ET_ClearsInTextObject()
    {
        var parser = CreateParser();
        bool? afterEt = null;

        parser.OnOperator += (op, _, _) =>
        {
            if (op == "ET") afterEt = parser.State.InTextObject;
        };

        var content = Encoding.ASCII.GetBytes("BT ET");
        parser.Parse(content);

        Assert.False(afterEt);
    }