[Test]
    public void Load_TooLongLayerMask_Throws()
    {
        byte[] bytes = File.ReadAllBytes(Path.Combine(TestContext.CurrentContext.TestDirectory, "testdata", "test.psd"));
        int colorModeLength = BigEndianBitConverter.ToInt32(bytes, 26);
        int resourcesLengthOffset = 26 + 4 + colorModeLength;
        int resourcesPayloadLength = BigEndianBitConverter.ToInt32(bytes, resourcesLengthOffset);
        int layerAndMaskLengthOffset = resourcesLengthOffset + 4 + resourcesPayloadLength;
        WriteUInt32BigEndian(bytes, layerAndMaskLengthOffset, 100000);
        using var stream = new MemoryStream(bytes);

        Assert.That(() => PsdImage.Load(stream), Throws.InstanceOf<PsdLoadException>());
    }