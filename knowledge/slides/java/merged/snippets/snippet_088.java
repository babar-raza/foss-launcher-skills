@Test
    void testConnectShapes() throws IOException {
        try (var pres = new Presentation()) {
            var slide = pres.getSlides().get(0);
            slide.getShapes().clear();
            var s1 = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 100, 60);
            var s2 = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 350, 200, 100, 60);
            var conn = slide.getShapes().addConnector(ShapeType.BENT_CONNECTOR3, 0, 0, 1, 1);

            conn.setStartShapeConnectedTo(s1);
            conn.setStartShapeConnectionSiteIndex(3);
            conn.setEndShapeConnectedTo(s2);
            conn.setEndShapeConnectionSiteIndex(1);

            assertThat(conn.getStartShapeConnectedTo()).isNotNull();
            assertThat(conn.getEndShapeConnectedTo()).isNotNull();

            try (var pres2 = saveAndReopen(pres)) {
                IConnector conn2 = null;
                var shapes2 = pres2.getSlides().get(0).getShapes();
                for (int i = 0; i < shapes2.size(); i++) {
                    IShape sh = shapes2.get(i);
                    if (sh.getShapeType() == ShapeType.BENT_CONNECTOR3) {
                        conn2 = (IConnector) sh;
                        break;
                    }
                }
                assertThat(conn2).isNotNull();
                assertThat(conn2.getStartShapeConnectionSiteIndex()).isEqualTo(3);
                assertThat(conn2.getEndShapeConnectionSiteIndex()).isEqualTo(1);
            }
        }
    }