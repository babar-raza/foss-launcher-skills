TEST(WorkbookPortingTests, HyperlinksValidationsAndConditionalFormattingRoundTrip)
{
    TempDir temp;
    const auto path = temp.Path("features.xlsx");

    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];
    sheet.GetCells()["A1"].PutValue(std::string_view("Docs"));
    const int linkIndex = sheet.GetHyperlinks().Add("A1", 1, 1, "https://example.com/docs");
    auto link = sheet.GetHyperlinks()[linkIndex];
    link.SetTextToDisplay("Docs");
    link.SetScreenTip("External docs");

    const int validationIndex = sheet.GetValidations().Add(CellArea::CreateCellArea("B1", "B3"));
    auto validation = sheet.GetValidations()[validationIndex];
    validation.SetType(ValidationType::List);
    validation.SetFormula1("\"Open,Closed\"");
    validation.SetShowError(true);
    validation.SetErrorTitle("Invalid");

    const int cfIndex = sheet.GetConditionalFormattings().Add();
    auto formatCollection = sheet.GetConditionalFormattings()[cfIndex];
    formatCollection.AddArea(CellArea::CreateCellArea("C1", "C3"));
    const int conditionIndex = formatCollection.AddCondition(
        FormatConditionType::CellValue,
        OperatorType::Between,
        "1",
        "9");
    auto condition = formatCollection[conditionIndex];
    condition.SetStopIfTrue(true);
    auto conditionStyle = condition.GetStyle();
    conditionStyle.SetPattern(FillPattern::Solid);
    conditionStyle.SetForegroundColor(Color::FromArgb(255, 255, 199, 206));
    condition.SetStyle(conditionStyle);

    workbook.Save(path.string());
    Workbook loaded(path.string());
    auto& loadedSheet = loaded.GetWorksheets()[0];

    ASSERT_EQ(1, loadedSheet.GetHyperlinks().GetCount());
    EXPECT_EQ("A1", loadedSheet.GetHyperlinks()[0].GetArea());
    EXPECT_EQ("https://example.com/docs", loadedSheet.GetHyperlinks()[0].GetAddress());
    EXPECT_EQ("Docs", loadedSheet.GetHyperlinks()[0].GetTextToDisplay());
    EXPECT_EQ("External docs", loadedSheet.GetHyperlinks()[0].GetScreenTip());

    ASSERT_EQ(1, loadedSheet.GetValidations().GetCount());
    auto loadedValidation = loadedSheet.GetValidations()[0];
    EXPECT_EQ(ValidationType::List, loadedValidation.GetType());
    EXPECT_EQ("\"Open,Closed\"", loadedValidation.GetFormula1());
    EXPECT_TRUE(loadedValidation.GetShowError());
    EXPECT_EQ("Invalid", loadedValidation.GetErrorTitle());

    ASSERT_EQ(1, loadedSheet.GetConditionalFormattings().GetCount());
    auto loadedFormatting = loadedSheet.GetConditionalFormattings()[0];
    ASSERT_EQ(1, loadedFormatting.GetCount());
    auto loadedCondition = loadedFormatting[0];
    EXPECT_EQ(FormatConditionType::CellValue, loadedCondition.GetType());
    EXPECT_EQ(OperatorType::Between, loadedCondition.GetOperator());
    EXPECT_EQ("1", loadedCondition.GetFormula1());
    EXPECT_EQ("9", loadedCondition.GetFormula2());
    EXPECT_TRUE(loadedCondition.GetStopIfTrue());
    EXPECT_EQ(FillPattern::Solid, loadedCondition.GetStyle().GetPattern());
}