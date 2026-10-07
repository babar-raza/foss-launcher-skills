protected static byte[] ReadLayerAndMaskTail(byte[] documentBytes)
    {
        const int headerLength = 26;
        int colorModeLength = BigEndianBitConverter.ToInt32(documentBytes, headerLength);
        int resourcesLengthOffset = headerLength + 4 + colorModeLength;
        int resourcesPayloadLength = BigEndianBitConverter.ToInt32(documentBytes, resourcesLengthOffset);
        int layerAndMaskLengthOffset = resourcesLengthOffset + 4 + resourcesPayloadLength;
        int layerAndMaskLength = BigEndianBitConverter.ToInt32(documentBytes, layerAndMaskLengthOffset);
        int layerInfoLength = ReadLayerInfoLength(documentBytes);
        int tailOffset = layerAndMaskLengthOffset + 4 + 4 + layerInfoLength;
        int tailLength = (layerAndMaskLengthOffset + 4 + layerAndMaskLength) - tailOffset;

        if (tailLength <= 0)
        {
            return [];
        }

        byte[] tailBytes = new byte[tailLength];
        Buffer.BlockCopy(documentBytes, tailOffset, tailBytes, 0, tailLength);
        return tailBytes;
    }