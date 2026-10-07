[Test]
    public void Load_NonZeroReserved_Throws()
    {
        byte[] bytes = BuildHeaderBytes(PsdHeader.PsdVersion);
        bytes[6] = 1;
        using var stream = new MemoryStream(bytes);
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        Assert.That(() => PsdHeader.Load(reader), Throws.InstanceOf<PsdLoadException>());
    }