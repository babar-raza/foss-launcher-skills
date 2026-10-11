private static int findPrecedingObjStart(byte[] data, int pos) {
        // Search backwards for " obj\n"
        byte[] needle = " obj\n".getBytes(StandardCharsets.US_ASCII);
        for (int i = pos - needle.length; i >= 0; i--) {
            boolean match = true;
            for (int j = 0; j < needle.length; j++) {
                if (data[i + j] != needle[j]) { match = false; break; }
            }
            if (match) return i + needle.length;
        }
        return -1;
    }