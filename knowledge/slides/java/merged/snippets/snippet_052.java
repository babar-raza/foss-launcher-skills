@Test
    void testLineDashStyle() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            var lf = shape.getLineFormat();
            lf.setWidth(3);
            lf.setDashStyle(LineDashStyle.DASH);
            lf.getFillFormat().setFillType(FillType.SOLID);
            lf.getFillFormat().getSolidFillColor().setColor(Color.BLACK);

            try (var pres2 = saveAndReopen(pres)) {
                var lf2 = pres2.getSlides().get(0).getShapes().get(0).getLineFormat();
                assertThat(lf2.getDashStyle()).isEqualTo(LineDashStyle.DASH);
            }
        }
    }