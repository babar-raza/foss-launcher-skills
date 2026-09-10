@Test
    void testAdjustmentProperties() {
        try (var pres = new Presentation()) {
            var conn = pres.getSlides().get(0).getShapes().addConnector(ShapeType.BENT_CONNECTOR3, 50, 50, 300, 200);
            if (conn.getAdjustments().size() > 0) {
                var adj = conn.getAdjustments().get(0);
                assertThat(adj.getName()).isNotNull();
                assertThat(adj.getRawValue()).isInstanceOf(Long.class);
                assertThat(adj.getAngleValue()).isInstanceOf(Double.class);
            }
        }
    }