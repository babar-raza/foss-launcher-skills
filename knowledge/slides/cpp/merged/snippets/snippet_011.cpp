TEST_F(ConnectorIntegrationTest, BentConnectorAdjustments) {
    Presentation pres;
    pres.slides()[0].shapes().clear();
    auto& conn = pres.slides()[0].shapes().add_connector(
        ShapeType::BENT_CONNECTOR3, 50, 50, 300, 200);
    if (conn.adjustments().size() > 0) {
        conn.adjustments()[0].set_raw_value(30000);
    }

    auto pres2 = save_and_reopen(pres);
    // Find the connector shape
    Connector* conn2 = nullptr;
    for (std::size_t i = 0; i < pres2.slides()[0].shapes().size(); ++i) {
        auto* c = dynamic_cast<Connector*>(&pres2.slides()[0].shapes()[i]);
        if (c) {
            conn2 = c;
            break;
        }
    }
    ASSERT_NE(conn2, nullptr) << "Connector not found after reload";
    if (conn2->adjustments().size() > 0) {
        EXPECT_EQ(conn2->adjustments()[0].raw_value(), 30000);
    }
}