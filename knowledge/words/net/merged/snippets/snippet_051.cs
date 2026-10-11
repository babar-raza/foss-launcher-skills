private static void CheckFont(Font font, string expectedFontName, double expectedFontSize, Color expectedColor,
            Color expectedHighlightColor, bool expectedBold, bool expectedItalic, Underline expectedUnderline,
            int expectedKerning, int expectedSpacing, bool expectedDoubleStrikeThrough, bool expectedStrikeThrough,
            bool expectedAllCaps, bool expectedSmallCaps, RunVerticalAlignment expectedVerticalAlignment,
            int expectedLocaleId)
        {
            TestChartUtil.CheckFontProperties(font, expectedFontName, null, null, null, expectedFontSize,
                expectedKerning, expectedSpacing, expectedBold, expectedItalic, expectedStrikeThrough,
                expectedDoubleStrikeThrough, expectedAllCaps, expectedSmallCaps, expectedColor, expectedHighlightColor,
                expectedUnderline, expectedVerticalAlignment, expectedLocaleId);
        }