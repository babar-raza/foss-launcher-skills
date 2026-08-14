[Fact]
    public void ParseSubobjectPropertyStreamRejectsShortHeader()
    {
        Assert.Throws<MsgException>(() => MsgReader.ParseSubobjectPropertyStreamData(new byte[7]));
    }