@Test
    void testBentConnectorAdjustments() throws IOException {
        try (var pres = new Presentation()) {
            pres.getSlides().get(0).getShapes().clear();
            var conn = pres.getSlides().get(0).getShapes().addConnector(ShapeType.BENT_CONNECTOR3, 50, 50, 300, 200);
            if (conn.getAdjustments().size() > 0) {
                conn.getAdjustments().get(0).setRawValue(30000);
            }

            try (var pres2 = saveAndReopen(pres)) {
                // Find the connector shape
                Connector conn2 = null;
                var shapes2 = pres2.getSlides().get(0).getShapes();
                for (int i = 0; i < shapes2.size(); i++) {
                    IShape sh = shapes2.get(i);
                    if (sh instanceof Connector c) {
                        conn2 = c;
                        break;
                    }
                }
                assertThat(conn2).as("Connector not found after reload").isNotNull();
                if (conn2.getAdjustments().size() > 0) {
                    assertThat(conn2.getAdjustments().get(0).getRawValue()).isEqualTo(30000);
                }
            }
        }
    }