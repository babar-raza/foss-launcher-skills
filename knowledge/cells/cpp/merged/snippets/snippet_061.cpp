TEST(WorksheetFeatureUnitTests, worksheet_row_column_and_merge_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& sheet = workbook.GetWorksheets()[0];

    sheet.SetVisibilityType(VisibilityType::Hidden);
    sheet.GetCells().GetRows()[2].SetHeight(19.75);
    sheet.GetCells().GetRows()[4].SetIsHidden(true);
    sheet.GetCells().GetColumns()[1].SetWidth(25.5);
    sheet.GetCells().GetColumns()[3].SetIsHidden(true);
    sheet.GetCells().Merge(1, 1, 2, 3);

    EXPECT_EQ(VisibilityType::Hidden, sheet.GetVisibilityType());
    EXPECT_DOUBLE_EQ(19.75, sheet.GetCells().GetRows()[2].GetHeight().value_or(0.0));
    EXPECT_TRUE(sheet.GetCells().GetRows()[4].GetIsHidden());
    EXPECT_DOUBLE_EQ(25.5, sheet.GetCells().GetColumns()[1].GetWidth().value_or(0.0));
    EXPECT_TRUE(sheet.GetCells().GetColumns()[3].GetIsHidden());
    auto merged = sheet.GetCells().GetMergedCells();
    ASSERT_EQ(1u, merged.size());
    ExpectArea(merged[0], 1, 1, 2, 3);
    EXPECT_THROW(sheet.GetCells().Merge(2, 2, 2, 2), CellsException);
}