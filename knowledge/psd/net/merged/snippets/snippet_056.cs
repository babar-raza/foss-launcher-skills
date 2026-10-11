[Test]
    public void Load_PsbHeader_ReadsMetadata()
    {
        using var stream = new MemoryStream(BuildHeaderBytes(PsdHeader.PsbVersion));
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        PsdHeader header = PsdHeader.Load(reader);

        Assert.That(header.Version, Is.EqualTo(PsdHeader.PsbVersion));
        Assert.That(header.IsLargeDocument, Is.True);
        Assert.That(header.Width, Is.EqualTo(1));
        Assert.That(header.Height, Is.EqualTo(1));
        Assert.That(header.Channels, Is.EqualTo(3));
    }