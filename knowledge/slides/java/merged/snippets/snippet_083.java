@Test
    void testIterateShapes() {
        try (var pres = new Presentation()) {
            var slide = blankSlide(pres);
            slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            slide.getShapes().addAutoShape(ShapeType.ELLIPSE, 300, 50, 150, 150);
            List<IShape> shapes = new ArrayList<>();
            var shapeCollection = slide.getShapes();
            for (int i = 0; i < shapeCollection.size(); i++) {
                shapes.add(shapeCollection.get(i));
            }
            assertThat(shapes).hasSize(2);
        }
    }