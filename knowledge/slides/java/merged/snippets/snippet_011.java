@ParameterizedTest(name = "{0}")
    @MethodSource("effects")
    void enablingAnEffectMustWriteACompleteElement(String label, String tag,
                                                   Consumer<IEffectFormat> enable,
                                                   List<String> requiredAttributes,
                                                   List<String> requiredChildGroup)
            throws Exception {
        Path out = tempDir.resolve(tag.replace(':', '-') + ".pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            enable.accept(shape.getEffectFormat());
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> effects = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//a:effectLst/" + tag);
            assertThat(effects)
                    .as("<%s> elements written by the %s enabler in %s", tag, label, out)
                    .hasSize(1);
            Element effect = effects.get(0);

            for (String attribute : requiredAttributes) {
                assertThat(effect.hasAttribute(attribute))
                        .as("<%s> must carry the required attribute '%s'; it was written as %s",
                                tag, attribute, describe(effect))
                        .isTrue();
            }

            if (!requiredChildGroup.isEmpty()) {
                assertThat(PackageAssertions.childNames(effect))
                        .as("<%s> must carry one of %s; it was written as %s",
                                tag, requiredChildGroup, describe(effect))
                        .containsAnyElementsOf(requiredChildGroup);
            }
        }
    }