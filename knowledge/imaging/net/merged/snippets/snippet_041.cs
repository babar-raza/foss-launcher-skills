public static byte[] Psd(int width, int height, int depth = 8) =>
        new ByteBuilder()
            .Ascii("8BPS")
            .UInt16BE(1)
            .Zeros(6)
            .UInt16BE(3)
            .UInt32BE((uint)height)
            .UInt32BE((uint)width)
            .UInt16BE(depth)
            .UInt16BE(3)
            .ToArray();