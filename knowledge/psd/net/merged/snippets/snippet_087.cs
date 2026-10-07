protected static byte[] ExtractImageResourcesSection(byte[] documentBytes)
    {
        const int headerLength = 26;
        int colorModeLength = BigEndianBitConverter.ToInt32(documentBytes, headerLength);
        int resourcesLengthOffset = headerLength + 4 + colorModeLength;
        int resourcesPayloadLength = BigEndianBitConverter.ToInt32(documentBytes, resourcesLengthOffset);
        int totalSectionLength = 4 + resourcesPayloadLength;
        byte[] sectionBytes = new byte[totalSectionLength];
        Array.Copy(documentBytes, resourcesLengthOffset, sectionBytes, 0, totalSectionLength);
        return sectionBytes;
    }