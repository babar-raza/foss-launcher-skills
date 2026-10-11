TEST(WorksheetFeatureUnitTests, conditional_formatting_advanced_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    auto contains = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    contains.AddArea(CellArea::CreateCellArea("A1", "A10"));
    auto containsRule = contains[contains.AddCondition(FormatConditionType::ContainsText)];
    containsRule.SetFormula1("error");
    containsRule.SetPriority(2);

    auto timePeriod = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    timePeriod.AddArea(CellArea::CreateCellArea("B1", "B10"));
    auto timeRule = timePeriod[timePeriod.AddCondition(FormatConditionType::TimePeriod)];
    timeRule.SetTimePeriod("today");

    auto top10 = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    top10.AddArea(CellArea::CreateCellArea("C1", "C10"));
    auto topRule = top10[top10.AddCondition(FormatConditionType::Top10)];
    topRule.SetPercent(true);
    topRule.SetRank(10);

    auto colorScale = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    colorScale.AddArea(CellArea::CreateCellArea("D1", "D10"));
    auto colorRule = colorScale[colorScale.AddCondition(FormatConditionType::ColorScale)];
    colorRule.SetColorScaleCount(3);
    colorRule.SetMinColor(Color::FromArgb(255, 248, 105, 107));
    colorRule.SetMidColor(Color::FromArgb(255, 255, 235, 132));
    colorRule.SetMaxColor(Color::FromArgb(255, 99, 190, 123));

    auto dataBar = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    dataBar.AddArea(CellArea::CreateCellArea("E1", "E10"));
    auto dataBarRule = dataBar[dataBar.AddCondition(FormatConditionType::DataBar)];
    dataBarRule.SetBarColor(Color::FromArgb(255, 99, 142, 198));
    dataBarRule.SetShowBorder(true);
    dataBarRule.SetDirection("left-to-right");

    auto iconSet = sheet.GetConditionalFormattings()[sheet.GetConditionalFormattings().Add()];
    iconSet.AddArea(CellArea::CreateCellArea("F1", "F10"));
    auto iconSetRule = iconSet[iconSet.AddCondition(FormatConditionType::IconSet)];
    iconSetRule.SetIconSetType("4Arrows");
    iconSetRule.SetReverseIcons(true);
    iconSetRule.SetShowIconOnly(true);

    EXPECT_EQ(6, sheet.GetConditionalFormattings().GetCount());
    EXPECT_EQ(FormatConditionType::ContainsText, containsRule.GetType());
    EXPECT_EQ("error", containsRule.GetFormula1());
    EXPECT_EQ(2, containsRule.GetPriority());
    EXPECT_EQ("today", timeRule.GetTimePeriod());
    EXPECT_TRUE(topRule.GetPercent());
    EXPECT_EQ(10, topRule.GetRank());
    EXPECT_EQ(3, colorRule.GetColorScaleCount());
    EXPECT_EQ(Color::FromArgb(255, 248, 105, 107), colorRule.GetMinColor());
    EXPECT_EQ(Color::FromArgb(255, 99, 142, 198), dataBarRule.GetBarColor());
    EXPECT_TRUE(dataBarRule.GetShowBorder());
    EXPECT_EQ("4Arrows", iconSetRule.GetIconSetType());
    EXPECT_TRUE(iconSetRule.GetReverseIcons());
    EXPECT_TRUE(iconSetRule.GetShowIconOnly());
}