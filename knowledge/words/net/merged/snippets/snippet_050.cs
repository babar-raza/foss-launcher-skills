private static void CheckOrientation(ChartDataLabel dataLabel, ShapeTextOrientation expectedOrientation,
            int expectedRotation)
        {
            Assert.That(dataLabel.Orientation, Is.EqualTo(expectedOrientation));
            Assert.That(dataLabel.Rotation, Is.EqualTo(expectedRotation));
        }