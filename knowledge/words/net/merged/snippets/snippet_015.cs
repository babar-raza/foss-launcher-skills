[Test]
        public void TestExistingAxisTitle()
        {
            // Axis title text depends on current culture.
            SystemPal.SaveCulture();
            SystemPal.SetStandardCulture();
            try
            {
                Document doc = TestUtil.Open(@"Model\Charts\TestAxisTitle.docx");
                Chart chart1 = doc.FirstSection.Body.Shapes[0].Chart;

                ChartAxisTitle xTitle1 = chart1.AxisX.Title;
                CheckTitle(xTitle1, true, false, "Horizontal Axis");
                ChartAxisTitle yTitle1 = chart1.AxisY.Title;
                CheckTitle(yTitle1, true, false, "Vertical Axis ");

                xTitle1.Show = false;

                yTitle1.Overlay = true;
                yTitle1.Text = "Value";

                CheckTitle(xTitle1, false, false, "Horizontal Axis");
                CheckTitle(yTitle1, true, true, "Value");

                Chart chart4 = doc.FirstSection.Body.Shapes[3].Chart;

                ChartAxisTitle xTitle4 = chart4.AxisX.Title;
                CheckTitle(xTitle4, true, false, "Primary horizontal");
                ChartAxisTitle yTitle4 = chart4.AxisY.Title;
                CheckTitle(yTitle4, true, false, "Primary vertical");

                xTitle4.Text = null;
                yTitle4.Text = string.Empty;

                CheckTitle(xTitle4, true, false, "Axis Title");
                CheckTitle(yTitle4, true, false, "Axis Title");

                TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestExistingAxisTitle.docx");
            }
            finally
            {
                SystemPal.RestoreCulture();
            }
        }