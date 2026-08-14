@Test
    void testLineColorAndWidth() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            var lf = shape.getLineFormat();
            lf.setWidth(5);
            lf.getFillFormat().setFillType(FillType.SOLID);
            lf.getFillFormat().getSolidFillColor().setColor(Color.DARK_RED);

            try (var pres2 = saveAndReopen(pres)) {
                var lf2 = pres2.getSlides().get(0).getShapes().get(0).getLineFormat();
                assertThat(lf2.getWidth()).isEqualTo(5);
                assertThat(lf2.getFillFormat().getFillType()).isEqualTo(FillType.SOLID);
                var c = lf2.getFillFormat().getSolidFillColor().getColor();
                assertThat(c.getR()).isEqualTo(Color.DARK_RED.getR());
            }
        }
    }