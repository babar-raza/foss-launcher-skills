@Test
    void anIndependentReaderMustBeAbleToGetAtTheImageBehindThePicture() throws Exception {
        Path out = writeDeckWithPicture("readable.pptx", Files.readAllBytes(PNG));
        ThirdPartyReadBack.assertOpens(out);
        ThirdPartyReadBack.assertPicturesResolve(out, 0);
    }