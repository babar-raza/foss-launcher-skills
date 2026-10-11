@ParameterizedTest(name = "{0}")
    @EnumSource(PatternStyle.class)
    void aPatternFillMustNameAPatternTheStandardDefines(PatternStyle style) throws Exception {
        Path out = tempDir.resolve("pattern-"
                + style.name().toLowerCase(Locale.ROOT) + ".pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            shape.getFillFormat().setFillType(FillType.PATTERN);
            shape.getFillFormat().getPatternFormat().setPatternStyle(style);
            pres.save(out.toString(), SaveFormat.PPTX);
        }

        try (PptxPackage pkg = PptxPackage.open(out)) {
            List<Element> fills = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//a:pattFill");
            String slide = pkg.text("ppt/slides/slide1.xml");

            if (style == PatternStyle.NOT_DEFINED || style == PatternStyle.UNKNOWN) {
                assertThat(fills.stream().filter(f -> f.hasAttribute("prst")).toList())
                        .as("PatternStyle.%s names no pattern, so nothing may be written as "
                                + "its prst%n%s", style, slide)
                        .isEmpty();
                return;
            }

            // Asserted rather than skipped: a writer that stopped writing pattern fills
            // altogether would satisfy a test that returns early when it finds none.
            assertThat(fills)
                    .as("a:pattFill in slide 1 for PatternStyle.%s%n%s", style, slide)
                    .hasSize(1);
            Element fill = fills.get(0);
            assertThat(fill.hasAttribute("prst"))
                    .as("a:pattFill/@prst for PatternStyle.%s%n%s", style, slide)
                    .isTrue();
            assertThat(fill.getAttribute("prst"))
                    .as("a:pattFill/@prst written for PatternStyle.%s", style)
                    .isIn(ST_PRESET_PATTERN_VAL);
        }
    }