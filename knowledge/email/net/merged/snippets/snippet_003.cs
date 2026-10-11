[Fact]
    public void WriterRejectsDuplicateSiblingNamesUnderCfbOrdering()
    {
        var document = new CfbDocument();
        document.Root.AddStream(new CfbStream("ab", [1]));
        document.Root.AddStream(new CfbStream("AB", [2]));

        var error = Assert.Throws<CfbException>(() => CfbWriter.ToBytes(document));
        Assert.Contains("Duplicate sibling name", error.Message);
    }