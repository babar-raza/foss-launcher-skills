TEST(WorksheetFeatureUnitTests, defined_name_apis_mutate_expected_settings)
{
    Workbook workbook;
    workbook.GetWorksheets()[0].SetName("Data");
    workbook.GetWorksheets().Add("Scoped");

    auto total = workbook.GetDefinedNames()[workbook.GetDefinedNames().Add("Total", "=SUM(Data!$A$1:$A$2)")];
    total.SetHidden(true);
    total.SetComment("Workbook scope");

    auto scoped = workbook.GetDefinedNames()[workbook.GetDefinedNames().Add("Input", "'Scoped'!$B$2", 1)];
    scoped.SetComment("Local scope");

    EXPECT_EQ(2, workbook.GetDefinedNames().GetCount());
    EXPECT_EQ("Total", total.GetName());
    EXPECT_EQ("SUM(Data!$A$1:$A$2)", total.GetFormula());
    EXPECT_FALSE(total.GetLocalSheetIndex().has_value());
    EXPECT_TRUE(total.GetHidden());
    EXPECT_EQ("Workbook scope", total.GetComment());

    EXPECT_EQ("Input", scoped.GetName());
    EXPECT_EQ("'Scoped'!$B$2", scoped.GetFormula());
    EXPECT_EQ(1, scoped.GetLocalSheetIndex().value_or(-1));
    EXPECT_EQ("Local scope", scoped.GetComment());

    EXPECT_THROW(workbook.GetDefinedNames().Add("Total", "1"), CellsException);
    EXPECT_THROW(workbook.GetDefinedNames().Add("_xlnm.Print_Area", "A1"), CellsException);
    EXPECT_THROW(workbook.GetDefinedNames().Add("Broken", "1", 5), CellsException);

    scoped.SetName("Total");
    EXPECT_THROW(scoped.SetLocalSheetIndex(std::nullopt), CellsException);

    workbook.GetDefinedNames().RemoveAt(1);
    EXPECT_EQ(1, workbook.GetDefinedNames().GetCount());
    EXPECT_THROW(workbook.GetDefinedNames().RemoveAt(5), CellsException);
}