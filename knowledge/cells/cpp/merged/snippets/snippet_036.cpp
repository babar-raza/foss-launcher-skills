TEST(OpenXmlFeatureGoldenTests, worksheet_dimension_includes_merge_only_ranges)
{
    TempDir temp("golden-merge-dimension");
    const auto path = temp.Path("merge-only.xlsx");
    Workbook workbook;
    workbook.GetWorksheets()[0].SetName("MergeOnly");
    workbook.GetWorksheets()[0].GetCells().Merge(4, 5, 2, 2);
    workbook.Save(path.string());

    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");
    EXPECT_TRUE(Contains(worksheetXml, "dimension ref=\"F5:G6\""));
    EXPECT_TRUE(Contains(worksheetXml, "mergeCell ref=\"F5:G6\""));

    Workbook loaded(path.string());
    const auto merged = loaded.GetWorksheets()[0].GetCells().GetMergedCells();
    ASSERT_EQ(1u, merged.size());
    EXPECT_EQ(4, merged[0].GetFirstRow());
    EXPECT_EQ(5, merged[0].GetFirstColumn());
}