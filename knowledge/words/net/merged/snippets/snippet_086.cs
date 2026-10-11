private void CheckChartExLegendPosition(ChartLegend legend, LegendPosition expectedPosition,
            SidePosition expectedSidePosition, PositionAlignment expectedAlignment)
        {
            Assert.That(legend.Position, Is.EqualTo(expectedPosition));
            Assert.That(legend.SidePosition, Is.EqualTo(expectedSidePosition));
            Assert.That(legend.PositionAlignment, Is.EqualTo(expectedAlignment));
        }