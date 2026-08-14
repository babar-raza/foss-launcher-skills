@Test
    void testPatternFill() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            shape.getFillFormat().setFillType(FillType.PATTERN);
            var pf = shape.getFillFormat().getPatternFormat();
            pf.setPatternStyle(PatternStyle.PERCENT50);
            pf.getForeColor().setColor(Color.DARK_BLUE);
            pf.getBackColor().setColor(Color.LIGHT_YELLOW);

            try (var pres2 = saveAndReopen(pres)) {
                var ff2 = pres2.getSlides().get(0).getShapes().get(0).getFillFormat();
                assertThat(ff2.getFillType()).isEqualTo(FillType.PATTERN);
                assertThat(ff2.getPatternFormat().getPatternStyle()).isEqualTo(PatternStyle.PERCENT50);
            }
        }
    }