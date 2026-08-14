[Fact]
    public void MsgEnumsAreAvailable()
    {
        Assert.Equal((ushort)2, (ushort)PropertyTypeCode.PtypInteger16);
        Assert.Equal((ushort)0x0037, (ushort)CommonMessagePropertyId.Subject);
    }