TEST_F(ConnectorIntegrationTest, AddStraightConnectorPersists) {
    Presentation pres;
    pres.slides()[0].shapes().add_connector(
        ShapeType::STRAIGHT_CONNECTOR1, 100, 100, 300, 200);

    auto pres2 = save_and_reopen(pres);
    EXPECT_GE(pres2.slides()[0].shapes().size(), 1u);
}