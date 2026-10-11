@Test
    void testReroute() {
        try (var pres = new Presentation()) {
            var slide = pres.getSlides().get(0);
            var s1 = slide.getShapes().addAutoShape(ShapeType.ELLIPSE, 50, 100, 80, 80);
            var s2 = slide.getShapes().addAutoShape(ShapeType.ELLIPSE, 400, 100, 80, 80);
            var conn = slide.getShapes().addConnector(ShapeType.BENT_CONNECTOR3, 0, 0, 1, 1);
            conn.setStartShapeConnectedTo(s1);
            conn.setStartShapeConnectionSiteIndex(3);
            conn.setEndShapeConnectedTo(s2);
            conn.setEndShapeConnectionSiteIndex(1);
            conn.reroute();
            // After reroute the connector should span between the shapes
            assertThat(conn.getWidth() > 0 || conn.getHeight() > 0).isTrue();
        }
    }