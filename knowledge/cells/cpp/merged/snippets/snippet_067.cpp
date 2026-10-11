TEST(WorksheetFeatureUnitTests, validation_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    auto primary = sheet.GetValidations()[sheet.GetValidations().Add(CellArea::CreateCellArea("A1", "B2"))];
    primary.SetType(ValidationType::WholeNumber);
    primary.SetOperator(OperatorType::Between);
    primary.SetFormula1("=1");
    primary.SetFormula2("=10");
    primary.SetShowError(true);
    primary.SetErrorTitle("Whole Number");
    primary.SetErrorMessage("Enter 1-10");
    primary.AddArea(CellArea::CreateCellArea("D4", "D5"));

    EXPECT_EQ(1, sheet.GetValidations().GetCount());
    ASSERT_EQ(2u, primary.GetAreas().size());
    EXPECT_EQ("1", primary.GetFormula1());
    EXPECT_EQ("10", primary.GetFormula2());
    ASSERT_TRUE(sheet.GetValidations().GetValidationInCell(0, 0).has_value());
    EXPECT_EQ(ValidationType::WholeNumber, sheet.GetValidations().GetValidationInCell(0, 0)->GetType());
    ASSERT_TRUE(sheet.GetValidations().GetValidationInCell(4, 3).has_value());
    EXPECT_EQ(ValidationType::WholeNumber, sheet.GetValidations().GetValidationInCell(4, 3)->GetType());
    EXPECT_THROW(sheet.GetValidations().Add(CellArea::CreateCellArea("B2", "C3")), CellsException);

    auto second = sheet.GetValidations()[sheet.GetValidations().Add(CellArea::CreateCellArea("F1", "F1"))];
    second.SetType(ValidationType::List);
    second.SetFormula1("\"Y,N\"");
    EXPECT_EQ(2, sheet.GetValidations().GetCount());

    sheet.GetValidations().RemoveACell(0, 0);
    EXPECT_FALSE(sheet.GetValidations().GetValidationInCell(0, 0).has_value());
    EXPECT_TRUE(sheet.GetValidations().GetValidationInCell(0, 1).has_value());

    sheet.GetValidations().RemoveArea(CellArea::CreateCellArea("F1", "F1"));
    EXPECT_EQ(1, sheet.GetValidations().GetCount());
    EXPECT_THROW(sheet.GetValidations().RemoveACell(-1, 0), CellsException);
    EXPECT_THROW(static_cast<void>(sheet.GetValidations()[-1]), CellsException);
}