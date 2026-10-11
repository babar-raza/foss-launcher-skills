@Test
    void anAddedSlideMustBeRegisteredInTheSavedFile() throws Exception {
        Path out = tempDir.resolve("added.pptx");
        try (var pres = new Presentation()) {
            ILayoutSlide layout = pres.getLayoutSlides().get(0);
            pres.getSlides().addEmptySlide(layout);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            PackageAssertions.assertRegisteredSlideCount(pkg, 2);
            PackageAssertions.assertPackageIsSelfConsistent(pkg);
        }
        assertThat(ThirdPartyReadBack.slideCount(out))
                .as("slides an independent reader finds in %s", out)
                .isEqualTo(2);
    }