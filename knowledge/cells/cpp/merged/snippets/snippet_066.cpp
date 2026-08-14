TEST(WorksheetFeatureUnitTests, hyperlink_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    sheet.GetCells()["A1"].PutValue("Docs");
    auto external = sheet.GetHyperlinks()[sheet.GetHyperlinks().Add("A1", 1, 1, "https://example.com/docs")];
    external.SetTextToDisplay("Docs");
    external.SetScreenTip("External docs");

    auto internalLink = sheet.GetHyperlinks()[sheet.GetHyperlinks().Add("B2", 1, 1, "Sheet1!C3")];
    internalLink.SetTextToDisplay("Jump");

    auto rangeLink = sheet.GetHyperlinks()[sheet.GetHyperlinks().Add("C4", 2, 2, "mailto:test@example.com")];
    rangeLink.SetScreenTip("Send mail");

    EXPECT_EQ(3, sheet.GetHyperlinks().GetCount());
    EXPECT_EQ("A1", external.GetArea());
    EXPECT_EQ("https://example.com/docs", external.GetAddress());
    EXPECT_EQ("External docs", external.GetScreenTip());
    EXPECT_EQ("Docs", external.GetTextToDisplay());
    EXPECT_EQ("B2", internalLink.GetArea());
    EXPECT_EQ("Sheet1!C3", internalLink.GetAddress());
    EXPECT_EQ("Jump", internalLink.GetTextToDisplay());
    EXPECT_EQ("C4:D5", rangeLink.GetArea());
    EXPECT_EQ("mailto:test@example.com", rangeLink.GetAddress());
    EXPECT_EQ("Send mail", rangeLink.GetScreenTip());

    EXPECT_THROW(sheet.GetHyperlinks().Add("A1", 1, 1, "https://overlap.example.com"), CellsException);
    EXPECT_THROW(sheet.GetHyperlinks().Add("Z1", 0, 1, "https://invalid.example.com"), CellsException);
    EXPECT_THROW(sheet.GetHyperlinks().Add("A2", 1, 1, ""), CellsException);
    EXPECT_THROW(static_cast<void>(sheet.GetHyperlinks()[-1]), CellsException);

    sheet.GetHyperlinks().RemoveAt(1);
    EXPECT_EQ(2, sheet.GetHyperlinks().GetCount());
    EXPECT_EQ("C4:D5", sheet.GetHyperlinks()[1].GetArea());
    EXPECT_THROW(sheet.GetHyperlinks().RemoveAt(99), CellsException);
}