[Fact]
    public void MarkedContent_BDC_SetsStateTag()
    {
        var parser = CreateParser();
        string? tagDuringBdc = null;
        string? tagAfterEmc = null;

        parser.OnMarkedContentBegin += (tag, _) => tagDuringBdc = parser.State.MarkedContentTag;
        parser.OnMarkedContentEnd += () => tagAfterEmc = parser.State.MarkedContentTag;

        var content = Encoding.ASCII.GetBytes("/P << /MCID 0 >> BDC\nEMC");
        parser.Parse(content);

        Assert.Equal("P", tagDuringBdc);
        Assert.Null(tagAfterEmc);
    }