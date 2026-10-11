[Fact]
    public void CfbConstantsAreAvailable()
    {
        Assert.Equal(0xFFFEu, CfbConstants.ByteOrderLittleEndian);
        Assert.Equal(0xFFFFFFFFu, CfbConstants.NOSTREAM);
        Assert.Equal("Root Entry", CfbConstants.RootEntryName);
    }