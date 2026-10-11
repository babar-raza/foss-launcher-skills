TEST(CompatibilityTests, compatibility_members_follow_aspose_style)
{
    Workbook workbook;
    workbook.GetSettings().SetDate1904(true);
    EXPECT_TRUE(workbook.GetSettings().GetDate1904());

    const auto index = workbook.GetWorksheets().Add();
    workbook.GetWorksheets()[index].SetName("Report");
    workbook.GetWorksheets().SetActiveSheetName("Report");
    EXPECT_EQ(index, workbook.GetWorksheets().GetActiveSheetIndex());

    auto& sheet = workbook.GetWorksheets()[index];
    sheet.SetVisibilityType(VisibilityType::Hidden);
    EXPECT_EQ(VisibilityType::Hidden, sheet.GetVisibilityType());

    sheet.GetCells()["A1"].SetValue("Docs");
    const auto hyperlinkIndex = sheet.GetHyperlinks().Add(0, 0, 1, 1, "https://example.com/docs");
    auto hyperlink = sheet.GetHyperlinks()[hyperlinkIndex];
    EXPECT_EQ(TargetModeType::External, hyperlink.GetLinkType());
    hyperlink.Delete();
    EXPECT_EQ(0, sheet.GetHyperlinks().GetCount());

    auto validation = sheet.GetValidations()[sheet.GetValidations().Add(CellArea::CreateCellArea("B2", "B2"))];
    validation.SetType(ValidationType::List);
    validation.SetFormula1("\"Yes,No\"");
    ASSERT_TRUE(sheet.GetValidations().GetValidationInCell(1, 1).has_value());
    EXPECT_EQ(ValidationType::List, sheet.GetValidations().GetValidationInCell(1, 1)->GetType());

    auto conditionalFormatting = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    conditionalFormatting.AddArea(CellArea::CreateCellArea("C3", "C3"));
    conditionalFormatting.AddCondition(FormatConditionType::Expression, OperatorType::None, "C3>0", "");
    EXPECT_EQ(1, sheet.GetConditionalFormattings().GetCount());

    auto& pageSetup = sheet.GetPageSetup();
    pageSetup.SetLeftMargin(1.27);
    EXPECT_DOUBLE_EQ(0.5, pageSetup.GetLeftMarginInch());
}