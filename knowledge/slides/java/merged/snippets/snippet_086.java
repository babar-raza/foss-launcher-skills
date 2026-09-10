@Test
    void testAddStraightConnectorPersists() throws IOException {
        try (var pres = new Presentation()) {
            pres.getSlides().get(0).getShapes().addConnector(ShapeType.STRAIGHT_CONNECTOR1, 100, 100, 300, 200);

            try (var pres2 = saveAndReopen(pres)) {
                assertThat(pres2.getSlides().get(0).getShapes().size()).isGreaterThanOrEqualTo(1);
            }
        }
    }