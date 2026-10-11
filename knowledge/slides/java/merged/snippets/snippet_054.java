@Test
    void anInsertedSlideMustBeRegisteredInTheSavedFile() throws Exception {
        Path out = tempDir.resolve("inserted.pptx");
        try (var pres = new Presentation()) {
            ILayoutSlide layout = pres.getLayoutSlides().get(0);
            pres.getSlides().insertEmptySlide(1, layout);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertRegisteredSlideCount(pkg, 2);
        }
    }