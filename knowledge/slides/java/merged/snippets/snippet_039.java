@Test
    void testNoFill() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            shape.getFillFormat().setFillType(FillType.NO_FILL);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().get(0).getShapes().get(0).getFillFormat().getFillType())
                        .isEqualTo(FillType.NO_FILL);
            }
        }
    }