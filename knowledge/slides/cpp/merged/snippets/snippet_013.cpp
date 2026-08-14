TEST(ConnectorIntegrationTestNoFixture, Reroute) {
    Presentation pres;
    auto& slide = pres.slides()[0];
    auto& s1 = slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 50, 100, 80, 80);
    auto& s2 = slide.shapes().add_auto_shape(ShapeType::ELLIPSE, 400, 100, 80, 80);
    auto& conn = slide.shapes().add_connector(ShapeType::BENT_CONNECTOR3, 0, 0, 1, 1);
    conn.set_start_shape_connected_to(&s1);
    conn.set_start_shape_connection_site_index(3);
    conn.set_end_shape_connected_to(&s2);
    conn.set_end_shape_connection_site_index(1);
    conn.reroute();
    // After reroute the connector should span between the shapes
    EXPECT_TRUE(conn.width() > 0 || conn.height() > 0);
}