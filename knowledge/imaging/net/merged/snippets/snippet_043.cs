public static byte[] Wmf(int width, int height)
    {
        const int inch = 1440;
        var right = width * inch / 96;
        var bottom = height * inch / 96;

        return new ByteBuilder()
            .Bytes(0x9A, 0xC6, 0xCD, 0xD7)
            .UInt16LE(0)
            .UInt16LE(0)
            .UInt16LE(0)
            .UInt16LE(right)
            .UInt16LE(bottom)
            .UInt16LE(inch)
            .UInt32LE(0)
            .UInt16LE(0)
            .ToArray();
    }