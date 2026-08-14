private static void CheckDataLabelPosition(ChartDataLabel dataLabel, ChartDataLabelPosition expectedPosition,
            double expectedLeft, ChartDataLabelLocationMode expectedLeftMode,
            double expectedTop, ChartDataLabelLocationMode expectedTopMode)
        {
            Assert.That(dataLabel.Position, Is.EqualTo(expectedPosition));
            Assert.That(dataLabel.Left, Is.EqualTo(expectedLeft).Within(0.15));
            Assert.That(dataLabel.LeftMode, Is.EqualTo(expectedLeftMode));
            Assert.That(dataLabel.Top, Is.EqualTo(expectedTop).Within(0.15));
            Assert.That(dataLabel.TopMode, Is.EqualTo(expectedTopMode));
        }