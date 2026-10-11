[Test]
    public void Load_PsdHeader_ReadsMetadata()
    {
        using var stream = new MemoryStream(BuildHeaderBytes(PsdHeader.PsdVersion));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        PsdHeader header = PsdHeader.Load(reader);

        Assert.That(header.Version, Is.EqualTo(PsdHeader.PsdVersion));
        Assert.That(header.Width, Is.EqualTo(1));
        Assert.That(header.Height, Is.EqualTo(1));
        Assert.That(header.Channels, Is.EqualTo(3));
        Assert.That(header.BitDepth, Is.EqualTo(8));
        Assert.That(header.ColorMode, Is.EqualTo(ColorModes.Rgb));
    }