protected static int ReadLayerInfoLength(byte[] documentBytes)
    {
        const int headerLength = 26;
        int colorModeLength = BigEndianBitConverter.ToInt32(documentBytes, headerLength);
        int resourcesLengthOffset = headerLength + 4 + colorModeLength;
        int resourcesPayloadLength = BigEndianBitConverter.ToInt32(documentBytes, resourcesLengthOffset);
        int layerAndMaskLengthOffset = resourcesLengthOffset + 4 + resourcesPayloadLength;
        int layerInfoLengthOffset = layerAndMaskLengthOffset + 4;
        return BigEndianBitConverter.ToInt32(documentBytes, layerInfoLengthOffset);
    }