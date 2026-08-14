@Test
    void testSolidFill() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            shape.getFillFormat().setFillType(FillType.SOLID);
            shape.getFillFormat().getSolidFillColor().setColor(Color.fromArgb(255, 0, 128, 255));

            try (var pres2 = saveAndReopen(pres)) {
                var ff = pres2.getSlides().get(0).getShapes().get(0).getFillFormat();
                assertThat(ff.getFillType()).isEqualTo(FillType.SOLID);
                var c = ff.getSolidFillColor().getColor();
                assertThat(c.getR()).isEqualTo(0);
                assertThat(c.getG()).isEqualTo(128);
                assertThat(c.getB()).isEqualTo(255);
            }
        }
    }