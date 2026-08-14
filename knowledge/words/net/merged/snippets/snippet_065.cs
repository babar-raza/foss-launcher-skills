[Test]
        public void TestDataTableProperties()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestDataTableFormat.docx");
            ShapeCollection shapes = doc.FirstSection.Body.Shapes;
            ChartDataTable dataTable1 = shapes[0].Chart.DataTable;
            ChartDataTable dataTable2 = shapes[1].Chart.DataTable;
            ChartDataTable dataTable3 = shapes[2].Chart.DataTable;
            ChartDataTable dataTable4 = shapes[3].Chart.DataTable;

            CheckDataTable(dataTable1, true, true, false, false, true);
            CheckDataTable(dataTable2, true, false, true, true, false);
            CheckDataTable(dataTable3, true, true, true, true, true);
            // This data table has borders, but Format.Stroke.Visible is 'false'.
            Assert.That(dataTable4.Format.Stroke.Visible, Is.False);
            CheckDataTable(dataTable4, true, false, true, true, true);

            // Change properties.

            dataTable1.HasLegendKeys = false;
            dataTable1.HasHorizontalBorder = true;
            dataTable1.HasVerticalBorder = true;
            dataTable1.HasOutlineBorder = false;

            dataTable2.HasLegendKeys = true;
            dataTable2.HasOutlineBorder = true;

            dataTable3.HasLegendKeys = false;
            dataTable3.HasHorizontalBorder = false;
            dataTable3.HasVerticalBorder = false;
            dataTable3.HasOutlineBorder = false;

            dataTable4.Show = false;

            TestUtil.SaveCheckGoldExportOnly(doc, @"Model\Charts\TestDataTableProperties.docx");
        }