[Fact]
    public void ParseSubobjectPropertyStreamRejectsMisalignedPayload()
    {
        var payload = new byte[11];
        Assert.Throws<MsgException>(() => MsgReader.ParseSubobjectPropertyStreamData(payload));
    }