private void CheckDataTable(ChartDataTable dataTable, bool isShown, bool hasLegendKeys,
            bool hasHorizontalBorder, bool hasVerticalBorder, bool hasOutlineBorder)
        {
            Assert.That(dataTable.Show, Is.EqualTo(isShown));
            Assert.That(dataTable.HasLegendKeys, Is.EqualTo(hasLegendKeys));
            Assert.That(dataTable.HasHorizontalBorder, Is.EqualTo(hasHorizontalBorder));
            Assert.That(dataTable.HasVerticalBorder, Is.EqualTo(hasVerticalBorder));
            Assert.That(dataTable.HasOutlineBorder, Is.EqualTo(hasOutlineBorder));
        }