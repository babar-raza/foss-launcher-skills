[Fact]
    public void MsgConstantsAreAvailable()
    {
        Assert.Equal("__properties_version1.0", MsgConstants.PropertyStreamName);
        Assert.Equal("__attach_version1.0_#", MsgConstants.AttachmentStoragePrefix);
    }