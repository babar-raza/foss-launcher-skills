private static void CheckTitle(ChartAxisTitle title, bool expectedShow, bool expectedOverlay, string expectedText)
        {
            Assert.That(title.Show, Is.EqualTo(expectedShow));
            Assert.That(title.Overlay, Is.EqualTo(expectedOverlay));
            Assert.That(title.Text, Is.EqualTo(expectedText));
        }