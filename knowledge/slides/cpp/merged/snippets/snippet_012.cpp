TEST_F(ConnectorIntegrationTest, ConnectShapes) {
    Presentation pres;
    auto& slide = pres.slides()[0];
    slide.shapes().clear();
    auto& s1 = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 50, 50, 100, 60);
    auto& s2 = slide.shapes().add_auto_shape(ShapeType::RECTANGLE, 350, 200, 100, 60);
    auto& conn = slide.shapes().add_connector(ShapeType::BENT_CONNECTOR3, 0, 0, 1, 1);

    conn.set_start_shape_connected_to(&s1);
    conn.set_start_shape_connection_site_index(3);
    conn.set_end_shape_connected_to(&s2);
    conn.set_end_shape_connection_site_index(1);

    ASSERT_NE(conn.start_shape_connected_to(), nullptr);
    ASSERT_NE(conn.end_shape_connected_to(), nullptr);

    auto pres2 = save_and_reopen(pres);
    Connector* conn2 = nullptr;
    for (std::size_t i = 0; i < pres2.slides()[0].shapes().size(); ++i) {
        auto& sh = pres2.slides()[0].shapes()[i];
        if (sh.shape_type() == ShapeType::BENT_CONNECTOR3) {
            conn2 = dynamic_cast<Connector*>(&sh);
            break;
        }
    }
    ASSERT_NE(conn2, nullptr);
    EXPECT_EQ(conn2->start_shape_connection_site_index(), 3u);
    EXPECT_EQ(conn2->end_shape_connection_site_index(), 1u);
}