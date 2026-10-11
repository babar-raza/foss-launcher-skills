private static void CheckOrientation(AxisTickLabels tickLabels, ShapeTextOrientation expectedOrientation,
            int expectedRotation)
        {
            Assert.That(tickLabels.Orientation, Is.EqualTo(expectedOrientation));
            Assert.That(tickLabels.Rotation, Is.EqualTo(expectedRotation));
        }