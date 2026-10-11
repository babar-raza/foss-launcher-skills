public static byte[] Dicom() =>
        new ByteBuilder()
            .Zeros(128)
            .Ascii("DICM")
            .ToArray();