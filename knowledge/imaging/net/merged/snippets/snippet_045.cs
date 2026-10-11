public static byte[] DicomWithPixelInfo(
        int rows,
        int columns,
        int bitsAllocated,
        string transferSyntax = ExplicitVrLittleEndian)
    {
        var builder = new ByteBuilder().Zeros(128).Ascii("DICM");
        AppendTransferSyntax(builder, transferSyntax);

        if (transferSyntax == ImplicitVrLittleEndian)
        {
            AppendImplicitUShort(builder, 0x0028, 0x0010, rows);
            AppendImplicitUShort(builder, 0x0028, 0x0011, columns);
            AppendImplicitUShort(builder, 0x0028, 0x0100, bitsAllocated);
        }
        else if (transferSyntax == ExplicitVrBigEndian)
        {
            AppendExplicitUShortBigEndian(builder, 0x0028, 0x0010, rows);
            AppendExplicitUShortBigEndian(builder, 0x0028, 0x0011, columns);
            AppendExplicitUShortBigEndian(builder, 0x0028, 0x0100, bitsAllocated);
        }
        else
        {
            AppendExplicitUShort(builder, 0x0028, 0x0010, rows);
            AppendExplicitUShort(builder, 0x0028, 0x0011, columns);
            AppendExplicitUShort(builder, 0x0028, 0x0100, bitsAllocated);
        }

        return builder.ToArray();
    }