TEST(ConnectorIntegrationTestNoFixture, AdjustmentProperties) {
    Presentation pres;
    auto& conn = pres.slides()[0].shapes().add_connector(
        ShapeType::BENT_CONNECTOR3, 50, 50, 300, 200);
    if (conn.adjustments().size() > 0) {
        auto& adj = conn.adjustments()[0];
        EXPECT_FALSE(adj.name().empty());
        // raw_value is int, angle_value is double — just verify they are accessible
        [[maybe_unused]] int rv = adj.raw_value();
        [[maybe_unused]] double av = adj.angle_value();
    }
}