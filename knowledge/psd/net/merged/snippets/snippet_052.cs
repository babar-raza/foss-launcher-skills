[Test]
    public void ReadAligned4_ConsumesPadding()
    {
        using var stream = new MemoryStream([0x00, 0x00, 0x00, 0x00, 0x7F]);
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        string value = reader.ReadPascalStringAlignedTo4();

        Assert.That(value, Is.Empty);
        Assert.That(reader.Position, Is.EqualTo(4));
        Assert.That(reader.ReadByte(), Is.EqualTo(0x7F));
    }