TEST(WorksheetFeatureUnitTests, conditional_formatting_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    auto collection = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    collection.AddArea(CellArea::CreateCellArea("A1", "A3"));
    auto condition = collection[collection.AddCondition(FormatConditionType::CellValue, OperatorType::Between, "=1", "=9")];
    condition.SetStopIfTrue(true);
    condition.SetPriority(1);
    auto style = condition.GetStyle();
    style.SetPattern(FillPattern::Solid);
    style.SetForegroundColor(Color::FromArgb(255, 255, 0, 0));
    condition.SetStyle(style);

    EXPECT_EQ(1, sheet.GetConditionalFormattings().GetCount());
    EXPECT_EQ(1, collection.GetRangeCount());
    EXPECT_EQ(1, collection.GetCount());
    EXPECT_EQ("1", condition.GetFormula1());
    EXPECT_EQ("9", condition.GetFormula2());
    EXPECT_TRUE(condition.GetStopIfTrue());
    EXPECT_EQ(FillPattern::Solid, condition.GetStyle().GetPattern());

    collection.AddCondition(FormatConditionType::Expression);
    EXPECT_EQ(2, collection.GetCount());
    collection.RemoveCondition(1);
    EXPECT_EQ(1, collection.GetCount());

    collection.AddArea(CellArea::CreateCellArea("C1", "C2"));
    EXPECT_EQ(2, collection.GetRangeCount());
    collection.RemoveArea(0, 0, 1, 1);
    EXPECT_EQ(2, collection.GetRangeCount());
    EXPECT_EQ(0, collection.GetCellArea(0).GetFirstRow());
    EXPECT_EQ(2, collection.GetCellArea(0).GetFirstColumn());

    sheet.GetConditionalFormattings().RemoveArea(0, 2, 2, 1);
    EXPECT_EQ(1, sheet.GetConditionalFormattings().GetCount());
    sheet.GetConditionalFormattings().RemoveAt(0);
    EXPECT_EQ(0, sheet.GetConditionalFormattings().GetCount());
    EXPECT_THROW(static_cast<void>(sheet.GetConditionalFormattings()[-1]), CellsException);
}