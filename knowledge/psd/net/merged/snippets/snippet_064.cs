[Test]
    public void Load_InvalidSignature_Throws()
    {
        using var stream = new MemoryStream(BuildHeaderBytes(PsdHeader.PsdVersion));
        using var reader = new BigEndianReader(stream, leaveOpen: true);
        stream.Position = 0;
        stream.WriteByte((byte)'B');
        stream.Position = 0;

        Assert.That(() => PsdHeader.Load(reader), Throws.InstanceOf<PsdLoadException>());
    }