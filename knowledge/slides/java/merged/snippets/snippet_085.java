@Test
    void testAddStraightConnector() {
        try (var pres = new Presentation()) {
            var slide = pres.getSlides().get(0);
            var conn = slide.getShapes().addConnector(ShapeType.STRAIGHT_CONNECTOR1, 100, 100, 300, 200);
            assertThat(conn.getShapeType()).isEqualTo(ShapeType.STRAIGHT_CONNECTOR1);
        }
    }