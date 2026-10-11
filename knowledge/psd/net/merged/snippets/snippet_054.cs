[TestCase(0, 1, 1, 8, (ushort)ColorModes.Rgb)]
    [TestCase(57, 1, 1, 8, (ushort)ColorModes.Rgb)]
    [TestCase(3, 0, 1, 8, (ushort)ColorModes.Rgb)]
    [TestCase(3, 1, 0, 8, (ushort)ColorModes.Rgb)]
    [TestCase(3, 30001, 1, 8, (ushort)ColorModes.Rgb)]
    [TestCase(3, 1, 1, 12, (ushort)ColorModes.Rgb)]
    [TestCase(3, 1, 1, 8, 99)]
    public void Load_InvalidHeaderField_Throws(
        int channels,
        int width,
        int height,
        int bitDepth,
        int colorMode)
    {
        byte[] bytes = BuildHeaderBytes(PsdHeader.PsdVersion, (ushort)channels, width, height, (ushort)bitDepth, (ColorModes)colorMode);
        using var stream = new MemoryStream(bytes);
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        Assert.That(() => PsdHeader.Load(reader), Throws.InstanceOf<PsdLoadException>());
    }