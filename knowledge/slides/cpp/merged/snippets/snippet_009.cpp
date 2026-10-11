TEST(ConnectorIntegrationTestNoFixture, AddStraightConnector) {
    Presentation pres;
    auto& slide = pres.slides()[0];
    auto& conn = slide.shapes().add_connector(
        ShapeType::STRAIGHT_CONNECTOR1, 100, 100, 300, 200);
    EXPECT_EQ(conn.shape_type(), ShapeType::STRAIGHT_CONNECTOR1);
}