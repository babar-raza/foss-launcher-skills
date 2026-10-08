@Test
    public void rc4_roundTrip_shortString() {
        PDFEncryptionDict encDict = buildRC4Dict();
        byte[] key = new byte[16];
        Arrays.fill(key, (byte) 0x42);

        PDFEncryptor encryptor = new PDFEncryptor(key, encDict);
        PDFDecryptor decryptor = new PDFDecryptor(key, encDict);

        byte[] plaintext = "Hello PDF".getBytes();
        byte[] encrypted = encryptor.encrypt(plaintext, 1, 0);
        byte[] decrypted = decryptor.decrypt(encrypted, 1, 0);
        assertArrayEquals(plaintext, decrypted);
    }