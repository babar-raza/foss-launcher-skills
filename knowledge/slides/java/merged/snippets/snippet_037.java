@Test
    void testGradientFill() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 300, 150);
            shape.getFillFormat().setFillType(FillType.GRADIENT);
            var gf = shape.getFillFormat().getGradientFormat();
            gf.setGradientShape(GradientShape.LINEAR);
            gf.setLinearGradientAngle(45);
            gf.getGradientStops().add(0.0, Color.BLUE);
            gf.getGradientStops().add(1.0, Color.RED);

            try (var pres2 = saveAndReopen(pres)) {
                var ff2 = pres2.getSlides().get(0).getShapes().get(0).getFillFormat();
                assertThat(ff2.getFillType()).isEqualTo(FillType.GRADIENT);
                assertThat(ff2.getGradientFormat().getGradientStops().size()).isGreaterThanOrEqualTo(2);
            }
        }
    }