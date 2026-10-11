[Fact]
    public void ParseTopLevelPropertyStreamRejectsMisalignedPayload()
    {
        var payload = new byte[29];
        Assert.Throws<MsgException>(() => MsgReader.ParseTopLevelPropertyStream(payload));
    }