TEST(WorksheetFeatureUnitTests, page_setup_apis_mutate_expected_settings)
{
    Workbook workbook;
    auto& pageSetup = workbook.GetWorksheets()[0].GetPageSetup();

    pageSetup.SetLeftMargin(0.508);
    pageSetup.SetRightMargin(0.635);
    pageSetup.SetOrientation(PageOrientationType::Landscape);
    pageSetup.SetPaperSize(PaperSizeType::PaperA4);
    pageSetup.SetFirstPageNumber(2);
    pageSetup.SetScale(90);
    pageSetup.SetFitToPagesWide(1);
    pageSetup.SetFitToPagesTall(3);
    pageSetup.SetPrintArea("$A$1:$D$20");
    pageSetup.SetPrintTitleRows("$1:$2");
    pageSetup.SetPrintTitleColumns("$A:$B");
    pageSetup.SetLeftHeader("LH");
    pageSetup.SetCenterFooter("CF");
    pageSetup.SetPrintGridlines(true);
    pageSetup.SetCenterHorizontally(true);
    pageSetup.AddHorizontalPageBreak(5);
    pageSetup.AddVerticalPageBreak(2);

    EXPECT_DOUBLE_EQ(0.508, pageSetup.GetLeftMargin());
    EXPECT_DOUBLE_EQ(0.635, pageSetup.GetRightMargin());
    EXPECT_EQ(PageOrientationType::Landscape, pageSetup.GetOrientation());
    EXPECT_EQ(PaperSizeType::PaperA4, pageSetup.GetPaperSize());
    EXPECT_EQ(2, pageSetup.GetFirstPageNumber().value_or(0));
    EXPECT_EQ(90, pageSetup.GetScale().value_or(0));
    EXPECT_EQ(1, pageSetup.GetFitToPagesWide().value_or(0));
    EXPECT_EQ(3, pageSetup.GetFitToPagesTall().value_or(0));
    EXPECT_EQ("$A$1:$D$20", pageSetup.GetPrintArea());
    EXPECT_EQ("$1:$2", pageSetup.GetPrintTitleRows());
    EXPECT_EQ("$A:$B", pageSetup.GetPrintTitleColumns());
    EXPECT_EQ("LH", pageSetup.GetLeftHeader());
    EXPECT_EQ("CF", pageSetup.GetCenterFooter());
    EXPECT_TRUE(pageSetup.GetPrintGridlines());
    EXPECT_TRUE(pageSetup.GetCenterHorizontally());
    ASSERT_EQ(1u, pageSetup.GetHorizontalPageBreaks().size());
    EXPECT_EQ(5, pageSetup.GetHorizontalPageBreaks()[0]);
    ASSERT_EQ(1u, pageSetup.GetVerticalPageBreaks().size());
    EXPECT_EQ(2, pageSetup.GetVerticalPageBreaks()[0]);
    EXPECT_THROW(pageSetup.SetScale(5), CellsException);
    EXPECT_THROW(pageSetup.SetLeftMargin(-0.1), CellsException);
}