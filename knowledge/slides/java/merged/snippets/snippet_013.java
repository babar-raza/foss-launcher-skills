@Test
    void aPictureAddedFromBytesMustResolveItsRelationship() throws Exception {
        Path out = writeDeckWithPicture("from-bytes.pptx", Files.readAllBytes(PNG));
        assertPictureIsReachable(out, "png");
    }