[Fact]
    public void MarkedContent_EMC_FiresEndEvent()
    {
        var parser = CreateParser();
        var endCount = 0;

        parser.OnMarkedContentEnd += () => endCount++;

        var content = Encoding.ASCII.GetBytes("/P BMC\nEMC");
        parser.Parse(content);

        Assert.Equal(1, endCount);
    }