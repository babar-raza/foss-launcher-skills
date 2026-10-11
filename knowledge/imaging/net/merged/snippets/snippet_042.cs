public static byte[] Emf(int width, int height) =>
        new ByteBuilder()
            .UInt32LE(1)
            .UInt32LE(88)
            .Int32LE(0)
            .Int32LE(0)
            .Int32LE(width)
            .Int32LE(height)
            .Zeros(16)
            .Bytes(0x20, 0x45, 0x4D, 0x46)
            .ToArray();