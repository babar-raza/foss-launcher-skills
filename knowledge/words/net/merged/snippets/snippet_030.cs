[Test]
        public void TestShowDataLabelsRangeOfCollection()
        {
            Document doc = CreateDocumentWithChart();
            Chart chart = doc.FirstSection.Body.Shapes[0].Chart;
            ChartSeries series = chart.Series[0];

            series.HasDataLabels = true;
            ChartDataLabelCollection labels = series.DataLabels;
            labels.ShowValue = true;
            labels.ShowDataLabelsRange = true;
            Assert.That(labels[1].ShowDataLabelsRange, Is.True);
            labels[1].ShowDataLabelsRange = false;

            series.DataLabelsRangeData.DataSource.ValueRef = new DmlChartValueRef(DmlChartValueType.String);
            series.DataLabelsRangeData.DataSource.ValueRef.Formula.Value = "Sheet1!$A$2:$A$5";

            DmlChartValueCollection valueCollection = series.DataLabelsRangeData.Values;
            valueCollection.Add(new DmlChartStrValue(0, "Text1"));
            valueCollection.Add(new DmlChartStrValue(1, "Text2"));
            valueCollection.Add(new DmlChartStrValue(2, "Text3"));
            valueCollection.ValueCount = 3;

            doc = TestUtil.SaveOpen(doc, @"Model\Charts\TestShowDataLabelsRangeOfCollection.docx", null, true);

            chart = doc.FirstSection.Body.Shapes[0].Chart;
            series = chart.Series[0];
            labels = series.DataLabels;

            Assert.That(labels.ShowValue, Is.True);
            Assert.That(labels.ShowDataLabelsRange, Is.True);

            foreach (ChartDataLabel label in labels)
            {
                bool isLabel1 = label.Index == 1;
                Assert.That(label.ShowDataLabelsRange, Is.EqualTo(!isLabel1));
                Assert.That(label.HasNonDefaultFormatting, Is.EqualTo(isLabel1));
            }
        }