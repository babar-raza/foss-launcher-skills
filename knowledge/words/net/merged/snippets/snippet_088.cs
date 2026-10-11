private static void CheckFont(Font font, string expectedFontName, double expectedFontSize, Color expectedColor,
            bool expectedBold, bool expectedItalic, Underline expectedUnderline)
        {
            Assert.That(font.Name, Is.EqualTo(expectedFontName));
            Assert.That(font.Size, Is.EqualTo(expectedFontSize).Within(0.1));
            Assert.That(font.Color, Is.EqualTo(expectedColor));
            Assert.That(font.Bold, Is.EqualTo(expectedBold));
            Assert.That(font.Italic, Is.EqualTo(expectedItalic));
            Assert.That(font.Underline, Is.EqualTo(expectedUnderline));
        }