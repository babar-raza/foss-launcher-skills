[Fact]
    public void ParseTopLevelPropertyStreamRejectsShortHeader()
    {
        Assert.Throws<MsgException>(() => MsgReader.ParseTopLevelPropertyStream(new byte[23]));
    }